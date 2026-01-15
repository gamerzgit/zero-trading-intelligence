"""
ZERO Truth Test Service - Milestone 7

Evaluates opportunity outcomes after market close and computes calibration factors.
Runs daily at 4pm ET (after market close) or can be triggered manually.

Per SPEC_LOCK §6: Truth Test Requirements
- Evaluate every opportunity emitted
- Compute realized MFE/MAE over exact horizon window
- Store results for calibration
- Publish calibration state to Redis
"""

import asyncio
import os
import sys
import logging
import json
from datetime import datetime, timedelta, timezone, time as dt_time
from typing import Optional, Dict, Any, List

import asyncpg
import redis.asyncio as redis
from aiohttp import web
import pytz

# Add project root to path for imports
project_root = os.path.join(os.path.dirname(__file__), '../../')
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from db import TruthTestDB
from evaluator import evaluate_opportunity, get_horizon_minutes
from calibration import aggregate_calibration

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Timezone
ET = pytz.timezone('America/New_York')
UTC = pytz.UTC


class TruthTestService:
    """
    Truth Test Service
    
    Runs daily after market close to evaluate opportunity outcomes
    and compute calibration factors.
    """
    
    def __init__(self):
        # Database config
        self.db_host = os.getenv('DB_HOST', 'timescaledb')
        self.db_port = int(os.getenv('DB_PORT', '5432'))
        self.db_name = os.getenv('DB_NAME', 'zero_trading')
        self.db_user = os.getenv('DB_USER', 'zero_user')
        self.db_password = os.getenv('DB_PASSWORD')
        
        # Redis config
        self.redis_host = os.getenv('REDIS_HOST', 'redis')
        self.redis_port = int(os.getenv('REDIS_PORT', '6379'))
        
        # API config
        self.api_port = int(os.getenv('TRUTH_TEST_API_PORT', '8004'))
        
        # State
        self.db_pool: Optional[asyncpg.Pool] = None
        self.redis_client: Optional[redis.Redis] = None
        self.db: Optional[TruthTestDB] = None
        self.is_running = False
        self.last_run_time: Optional[datetime] = None
        self.last_run_stats: Dict[str, Any] = {}
        self.start_time: Optional[datetime] = None
    
    async def connect_db(self):
        """Connect to TimescaleDB"""
        try:
            self.db_pool = await asyncpg.create_pool(
                host=self.db_host,
                port=self.db_port,
                database=self.db_name,
                user=self.db_user,
                password=self.db_password,
                min_size=2,
                max_size=10
            )
            self.db = TruthTestDB(self.db_pool)
            logger.info(f"✅ Database connected: {self.db_host}:{self.db_port}/{self.db_name}")
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            raise
    
    async def connect_redis(self):
        """Connect to Redis"""
        try:
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                decode_responses=True
            )
            await self.redis_client.ping()
            logger.info(f"✅ Redis connected: {self.redis_host}:{self.redis_port}")
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            raise
    
    async def run_truth_test(self, target_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Run truth test for a specific date or today.
        
        Args:
            target_date: Optional date string (YYYY-MM-DD) for backfill
        
        Returns:
            Stats dict with evaluation results
        """
        run_start = datetime.now(UTC)
        
        # Determine cutoff time (opportunities must be old enough for horizon to have elapsed)
        if target_date:
            # Backfill mode - evaluate opportunities from that date
            try:
                date_obj = datetime.strptime(target_date, "%Y-%m-%d")
                # Set cutoff to end of that trading day (4pm ET)
                cutoff_et = ET.localize(datetime.combine(date_obj.date(), dt_time(16, 0)))
                cutoff = cutoff_et.astimezone(UTC)
            except ValueError:
                logger.error(f"Invalid date format: {target_date}")
                return {"error": f"Invalid date format: {target_date}"}
        else:
            # Normal mode - evaluate opportunities old enough for longest horizon
            # HWEEK = 5 trading days, so need ~7 calendar days buffer
            cutoff = run_start - timedelta(days=7)
        
        logger.info(f"🔍 Running truth test with cutoff: {cutoff}")
        
        # Get unevaluated opportunities
        opportunities = await self.db.get_unevaluated_opportunities(cutoff)
        logger.info(f"📊 Found {len(opportunities)} unevaluated opportunities")
        
        stats = {
            "run_time": run_start.isoformat(),
            "cutoff": cutoff.isoformat(),
            "total_opportunities": len(opportunities),
            "evaluated": 0,
            "pass": 0,
            "fail": 0,
            "expired": 0,
            "no_data": 0,
            "errors": 0
        }
        
        for opp in opportunities:
            try:
                result = await self._evaluate_single_opportunity(opp, run_start)
                
                # Insert result
                await self.db.insert_performance_result(result)
                
                stats["evaluated"] += 1
                outcome = result["outcome"]
                if outcome == "PASS":
                    stats["pass"] += 1
                elif outcome == "FAIL":
                    stats["fail"] += 1
                elif outcome == "EXPIRED":
                    stats["expired"] += 1
                elif outcome == "NO_DATA":
                    stats["no_data"] += 1
                
            except Exception as e:
                logger.error(f"❌ Error evaluating opportunity {opp['id']}: {e}", exc_info=True)
                stats["errors"] += 1
        
        # Compute and publish calibration
        if stats["evaluated"] > 0:
            await self._update_calibration()
        
        self.last_run_time = run_start
        self.last_run_stats = stats
        
        logger.info(
            f"✅ Truth test complete: {stats['evaluated']} evaluated, "
            f"{stats['pass']} PASS, {stats['fail']} FAIL, "
            f"{stats['expired']} EXPIRED, {stats['no_data']} NO_DATA"
        )
        
        return stats
    
    async def _evaluate_single_opportunity(
        self, 
        opp: Dict[str, Any],
        evaluation_time: datetime
    ) -> Dict[str, Any]:
        """Evaluate a single opportunity"""
        ticker = opp["ticker"]
        issue_time = opp["time"]
        horizon = opp["horizon"]
        horizon_minutes = get_horizon_minutes(horizon)
        
        # Get entry candle (1m close at/after issue time)
        entry_candle = await self.db.get_entry_candle(ticker, issue_time)
        
        # Get ATR value
        atr_value = await self.db.compute_atr(ticker, issue_time)
        
        # Get forward candles for horizon window
        end_time = issue_time + timedelta(minutes=horizon_minutes)
        forward_candles = await self.db.get_candles_for_evaluation(
            ticker, issue_time, end_time, "1m"
        )
        
        # Evaluate
        result = evaluate_opportunity(
            opportunity=opp,
            entry_candle=entry_candle,
            forward_candles=forward_candles,
            atr_value=atr_value,
            evaluation_time=evaluation_time
        )
        
        return result
    
    async def _update_calibration(self):
        """Compute and publish calibration state to Redis"""
        try:
            # Get performance data for calibration
            performance_data = await self.db.get_calibration_data(lookback_days=30)
            
            if not performance_data:
                logger.warning("⚠️  No performance data for calibration")
                return
            
            # Aggregate and compute shrink factors
            calibration_state = aggregate_calibration(performance_data)
            
            # 1. Publish to Redis key (for core service to read)
            await self.redis_client.set(
                "key:calibration_state",
                json.dumps(calibration_state)
            )
            
            # 2. Also store confidence_multipliers separately for easy lookup
            await self.redis_client.set(
                "key:confidence_multipliers",
                json.dumps(calibration_state.get("confidence_multipliers", {}))
            )
            
            # 3. Publish key:probability_calibration in spec format
            # Format: { "H30": { "GREEN": { "STABLE": { "predicted": 0.70, "realized": 0.58, ... } } } }
            await self.redis_client.set(
                "key:probability_calibration",
                json.dumps(calibration_state.get("probability_calibration", {}))
            )
            
            # 3. Publish notification to chan:calibration_update (for dashboard)
            update_notification = {
                "timestamp": calibration_state["timestamp"],
                "degraded_horizons": calibration_state.get("degraded_horizons", []),
                "degraded_states": calibration_state.get("degraded_states", []),
                "confidence_multipliers": calibration_state.get("confidence_multipliers", {}),
                "global_stats": calibration_state.get("global_stats", {})
            }
            await self.redis_client.publish(
                "chan:calibration_update",
                json.dumps(update_notification)
            )
            
            # 4. Persist snapshot to calibration_log (survives restarts)
            try:
                snapshot_id = await self.db.insert_calibration_snapshot(calibration_state)
                logger.info(f"💾 Persisted calibration snapshot to DB: id={snapshot_id}")
            except Exception as db_err:
                # Don't fail the whole calibration if DB persist fails
                logger.warning(f"⚠️  Failed to persist calibration to DB: {db_err}")
            
            logger.info(
                f"✅ Calibration published: {len(calibration_state['buckets'])} buckets, "
                f"degraded_horizons={calibration_state.get('degraded_horizons', [])}, "
                f"degraded_states={calibration_state.get('degraded_states', [])}"
            )
            
        except Exception as e:
            logger.error(f"❌ Failed to update calibration: {e}", exc_info=True)
    
    async def _schedule_daily_run(self):
        """Schedule daily run at 4pm ET (after market close)"""
        while self.is_running:
            try:
                now_et = datetime.now(ET)
                
                # Target time: 4:05pm ET (5 minutes after close for data to settle)
                target_time = now_et.replace(hour=16, minute=5, second=0, microsecond=0)
                
                # If we've passed today's target, schedule for tomorrow
                if now_et >= target_time:
                    target_time += timedelta(days=1)
                
                # Skip weekends
                while target_time.weekday() >= 5:  # Saturday=5, Sunday=6
                    target_time += timedelta(days=1)
                
                wait_seconds = (target_time - now_et).total_seconds()
                
                logger.info(
                    f"⏰ Next scheduled run: {target_time.strftime('%Y-%m-%d %H:%M:%S ET')} "
                    f"(in {wait_seconds/3600:.1f} hours)"
                )
                
                # Wait until target time (check every minute for shutdown)
                while wait_seconds > 0 and self.is_running:
                    sleep_time = min(60, wait_seconds)
                    await asyncio.sleep(sleep_time)
                    wait_seconds -= sleep_time
                
                if self.is_running:
                    logger.info("🚀 Starting scheduled truth test run...")
                    await self.run_truth_test()
                
            except Exception as e:
                logger.error(f"❌ Error in scheduler: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait before retrying
    
    # HTTP Handlers
    async def health_handler(self, request):
        """Health check endpoint"""
        try:
            status = "healthy" if self.is_running else "starting"
            
            uptime = 0
            if self.start_time:
                uptime = (datetime.now(UTC) - self.start_time).total_seconds()
            
            health = {
                "service": "zero-truth-test",
                "status": status,
                "uptime_seconds": uptime,
                "last_run_time": self.last_run_time.isoformat() if self.last_run_time else None,
                "last_run_stats": self.last_run_stats,
                "db_connected": self.db_pool is not None,
                "redis_connected": self.redis_client is not None
            }
            
            return web.json_response(health)
        except Exception as e:
            return web.json_response(
                {"service": "zero-truth-test", "status": "unhealthy", "error": str(e)},
                status=500
            )
    
    async def run_handler(self, request):
        """
        Manual trigger endpoint: POST /run?date=YYYY-MM-DD
        
        If date is provided, runs backfill for that date.
        Otherwise runs for recent opportunities.
        """
        try:
            target_date = request.query.get("date")
            
            logger.info(f"📨 Manual trigger received, date={target_date}")
            
            stats = await self.run_truth_test(target_date)
            
            return web.json_response({
                "status": "completed",
                "stats": stats
            })
        except Exception as e:
            logger.error(f"❌ Manual run failed: {e}", exc_info=True)
            return web.json_response(
                {"status": "error", "error": str(e)},
                status=500
            )
    
    async def start(self):
        """Start the service"""
        self.is_running = True
        self.start_time = datetime.now(UTC)
        
        await self.connect_db()
        await self.connect_redis()
        
        # Setup HTTP server
        self.app = web.Application()
        self.app.router.add_get('/health', self.health_handler)
        self.app.router.add_post('/run', self.run_handler)
        
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, '0.0.0.0', self.api_port)
        await self.site.start()
        
        logger.info(f"✅ HTTP server started on port {self.api_port}")
        logger.info("🚀 ZERO Truth Test Service started")
        
        # Start scheduler
        await self._schedule_daily_run()
    
    async def stop(self):
        """Stop the service"""
        logger.info("🛑 Shutting down ZERO Truth Test Service...")
        self.is_running = False
        
        if self.redis_client:
            await self.redis_client.aclose()
        if self.db_pool:
            await self.db_pool.close()
        if hasattr(self, 'site'):
            await self.site.stop()
        if hasattr(self, 'runner'):
            await self.runner.cleanup()
        
        logger.info("✅ ZERO Truth Test Service stopped")


async def main():
    service = TruthTestService()
    
    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}", exc_info=True)
    finally:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())
