"""
ZERO Scanner Service (Level 2 - Opportunity Discovery)
Filters universe to find Active Candidates
"""

import asyncio
import os
import sys
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
import json

import asyncpg
import redis.asyncio as redis
from aiohttp import web
import pandas as pd

# Add parent directory to path for contracts
project_root = os.path.join(os.path.dirname(__file__), '../../')
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from contracts.schemas import CandidateList, MarketState, HealthCheck
from horizon import get_all_horizons, get_horizon_info
from filters import ScannerFilters

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ScannerService:
    """ZERO Scanner Service - Level 2 Opportunity Discovery"""
    
    def __init__(self):
        # Configuration
        self.db_host = os.getenv('DB_HOST', 'timescaledb')
        self.db_port = int(os.getenv('DB_PORT', '5432'))
        self.db_name = os.getenv('DB_NAME', 'zero_trading')
        self.db_user = os.getenv('DB_USER', 'zero_user')
        self.db_password = os.getenv('DB_PASSWORD')
        
        self.redis_host = os.getenv('REDIS_HOST', 'redis')
        self.redis_port = int(os.getenv('REDIS_PORT', '6379'))
        
        self.scan_interval = int(os.getenv('SCAN_INTERVAL_SECONDS', '60'))  # Scan every 60 seconds
        self.scan_universe = self._load_scan_universe()
        
        # Components
        self.db_pool: Optional[asyncpg.Pool] = None
        self.redis_client: Optional[redis.Redis] = None
        self.filters = ScannerFilters()
        
        # State
        self.is_running = False
        self.last_scan_time: Optional[datetime] = None
        self.current_candidates: Dict[str, List[str]] = {}  # horizon -> list of tickers
        
    def _load_scan_universe(self) -> List[str]:
        """Load scan universe (default: S&P 500)"""
        # Default universe - can be expanded later
        default_universe = [
            # Major indices
            "SPY", "QQQ", "IWM", "DIA",
            # Tech
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AMD",
            # Finance
            "JPM", "BAC", "GS", "MS",
            # Healthcare
            "JNJ", "PFE", "UNH",
            # Consumer
            "WMT", "HD", "NKE",
            # Energy
            "XOM", "CVX",
            # And more... (expand to 500+ in production)
        ]
        
        # TODO: Load from Redis key:scan_universe or config file
        return default_universe
    
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
            logger.info("✅ Connected to TimescaleDB")
        except Exception as e:
            logger.error(f"❌ Failed to connect to TimescaleDB: {e}")
            raise
    
    async def connect_redis(self):
        """Connect to Redis"""
        try:
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                decode_responses=False  # We'll decode manually
            )
            await self.redis_client.ping()
            logger.info("✅ Connected to Redis")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            raise
    
    async def get_market_state(self) -> Optional[MarketState]:
        """Get current MarketState from Redis"""
        if not self.redis_client:
            return None
        
        try:
            state_json = await self.redis_client.get("key:market_state")
            if not state_json:
                logger.warning("⚠️  MarketState not found in Redis")
                return None
            
            state_dict = json.loads(state_json.decode('utf-8'))
            return MarketState(**state_dict)
        except Exception as e:
            logger.error(f"❌ Failed to get MarketState: {e}")
            return None
    
    async def fetch_candles(
        self, 
        ticker: str, 
        timeframe: str = "5m",
        lookback_minutes: int = 240
    ) -> pd.DataFrame:
        """Fetch candles from database"""
        if not self.db_pool:
            return pd.DataFrame()
        
        table_name = f"candles_{timeframe}"
        
        try:
            query = f"""
                SELECT time, open, high, low, close, volume
                FROM {table_name}
                WHERE ticker = $1
                AND time >= NOW() - INTERVAL '{lookback_minutes} minutes'
                ORDER BY time ASC
            """
            
            rows = await self.db_pool.fetch(query, ticker)
            
            if not rows:
                return pd.DataFrame()
            
            # Convert to DataFrame
            data = {
                'time': [r['time'] for r in rows],
                'open': [float(r['open']) for r in rows],
                'high': [float(r['high']) for r in rows],
                'low': [float(r['low']) for r in rows],
                'close': [float(r['close']) for r in rows],
                'volume': [int(r['volume']) for r in rows]
            }
            
            return pd.DataFrame(data)
        except Exception as e:
            logger.error(f"❌ Failed to fetch candles for {ticker}: {e}")
            return pd.DataFrame()
    
    async def scan_horizon(self, horizon: str) -> List[str]:
        """Scan for candidates for a specific horizon"""
        candidates = []
        horizon_info = get_horizon_info(horizon)
        
        if not horizon_info:
            logger.warning(f"⚠️  Unknown horizon: {horizon}")
            return candidates
        
        lookback_minutes = horizon_info.get("lookback_minutes", 240)
        
        logger.info(f"🔍 Scanning {len(self.scan_universe)} tickers for {horizon}...")
        
        for ticker in self.scan_universe:
            try:
                # Fetch candles
                candles_5m = await self.fetch_candles(ticker, "5m", lookback_minutes)
                candles_1m = await self.fetch_candles(ticker, "1m", min(lookback_minutes, 60))  # Limit 1m to 60 min
                
                # Apply filters
                passed, stats = self.filters.apply_all_filters(ticker, candles_1m, candles_5m)
                
                if passed:
                    candidates.append(ticker)
                    logger.debug(f"✅ {ticker} passed filters for {horizon}")
                else:
                    logger.debug(f"❌ {ticker} failed {stats.get('filter', 'unknown')} filter")
                    
            except Exception as e:
                logger.error(f"❌ Error scanning {ticker}: {e}")
                continue
        
        logger.info(f"✅ Found {len(candidates)} candidates for {horizon}")
        return candidates
    
    async def scan_all_horizons(self) -> Dict[str, List[str]]:
        """Scan all horizons"""
        results = {}
        
        for horizon in get_all_horizons():
            candidates = await self.scan_horizon(horizon)
            results[horizon] = candidates
        
        return results
    
    async def publish_candidates(self, horizon: str, candidates: List[str]):
        """Publish candidates to Redis"""
        if not self.redis_client:
            return
        
        try:
            # Create CandidateList
            candidate_list = CandidateList(
                candidates=candidates,
                horizon=horizon,
                scan_time=datetime.now(timezone.utc),
                filter_stats={}  # Can add stats later
            )
            
            # Publish to channel
            channel = "chan:active_candidates"
            payload = candidate_list.model_dump_json().encode('utf-8')
            await self.redis_client.publish(channel, payload)
            
            # Store in key (with TTL)
            key = "key:active_candidates"
            await self.redis_client.setex(
                key,
                300,  # 5 minute TTL
                candidate_list.model_dump_json()
            )
            
            # Update last scan time
            await self.redis_client.set(
                "key:last_scan_time",
                datetime.now(timezone.utc).isoformat()
            )
            
            logger.info(f"✅ Published {len(candidates)} candidates for {horizon} to Redis")
        except Exception as e:
            logger.error(f"❌ Failed to publish candidates: {e}")
    
    async def log_candidates_to_db(self, horizon: str, candidates: List[str], market_state: MarketState):
        """Log candidates to opportunity_log (Level 2 - minimal data)"""
        if not self.db_pool or not candidates:
            return
        
        try:
            # For Level 2 candidates, we log with placeholder values for Level 3 fields
            query = """
                INSERT INTO opportunity_log (
                    time, ticker, horizon,
                    opportunity_score, probability, target_atr, stop_atr,
                    market_state, attention_stability_score, attention_bucket
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """
            
            now = datetime.now(timezone.utc)
            
            for ticker in candidates:
                await self.db_pool.execute(
                    query,
                    now,  # time
                    ticker,  # ticker
                    horizon,  # horizon
                    0.0,  # opportunity_score (Level 2 - no score yet)
                    0.0,  # probability (Level 2 - no probability yet)
                    0.0,  # target_atr (placeholder)
                    0.0,  # stop_atr (placeholder)
                    market_state.state,  # market_state
                    0.0,  # attention_stability_score (Level 1 not implemented)
                    None  # attention_bucket (NULL allowed)
                )
            
            logger.info(f"✅ Logged {len(candidates)} candidates for {horizon} to DB")
        except Exception as e:
            logger.error(f"❌ Failed to log candidates to DB: {e}")
    
    async def scan_loop(self):
        """Main scanning loop"""
        logger.info("🚀 Starting scanner loop...")
        
        while self.is_running:
            try:
                # Check MarketState - if RED, sleep
                market_state = await self.get_market_state()
                
                if not market_state:
                    logger.warning("⚠️  MarketState not available, sleeping...")
                    await asyncio.sleep(self.scan_interval)
                    continue
                
                if market_state.state == "RED":
                    logger.info("🔴 MarketState is RED - scanner sleeping")
                    await asyncio.sleep(self.scan_interval)
                    continue
                
                # Market is GREEN or YELLOW - proceed with scan
                logger.info(f"✅ MarketState is {market_state.state} - scanning...")
                
                # Scan all horizons
                results = await self.scan_all_horizons()
                
                # Publish results
                for horizon, candidates in results.items():
                    await self.publish_candidates(horizon, candidates)
                    await self.log_candidates_to_db(horizon, candidates, market_state)
                
                self.current_candidates = results
                self.last_scan_time = datetime.now()
                
                # Sleep until next scan
                await asyncio.sleep(self.scan_interval)
                
            except Exception as e:
                logger.error(f"❌ Error in scan loop: {e}")
                await asyncio.sleep(self.scan_interval)
    
    async def start(self):
        """Start the scanner service"""
        logger.info("🚀 Starting ZERO Scanner Service...")
        
        await self.connect_db()
        await self.connect_redis()
        
        self.is_running = True
        
        # Start scan loop
        await self.scan_loop()
    
    async def stop(self):
        """Stop the scanner service"""
        logger.info("🛑 Stopping scanner service...")
        self.is_running = False
        
        if self.db_pool:
            await self.db_pool.close()
        
        if self.redis_client:
            await self.redis_client.close()
    
    async def health_check(self) -> HealthCheck:
        """Health check endpoint"""
        details = {
            "is_running": self.is_running,
            "last_scan_time": self.last_scan_time.isoformat() if self.last_scan_time else None,
            "current_candidates": {
                horizon: len(candidates) 
                for horizon, candidates in self.current_candidates.items()
            },
            "scan_universe_size": len(self.scan_universe),
            "db_connected": self.db_pool is not None,
            "redis_connected": self.redis_client is not None
        }
        
        status = "healthy" if (self.is_running and self.db_pool and self.redis_client) else "unhealthy"
        
        return HealthCheck(
            service="zero-scanner",
            status=status,
            last_update=datetime.now(timezone.utc),
            details=details
        )


# HTTP server for health endpoint
async def health_handler(request):
    """Health check HTTP handler"""
    service = request.app['scanner_service']
    health = await service.health_check()
    return web.json_response(health.model_dump(mode='json'))


async def create_app():
    """Create aiohttp app"""
    app = web.Application()
    
    scanner_service = ScannerService()
    app['scanner_service'] = scanner_service
    
    app.router.add_get('/health', health_handler)
    
    return app, scanner_service


async def main():
    """Main entry point"""
    app, scanner_service = await create_app()
    
    # Start HTTP server
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.getenv('API_PORT', '8001'))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    logger.info(f"✅ Health endpoint listening on port {port}")
    
    try:
        await scanner_service.start()
    except KeyboardInterrupt:
        logger.info("🛑 Received shutdown signal")
    finally:
        await scanner_service.stop()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())

