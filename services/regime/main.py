"""
ZERO Regime Engine Service (Level 0 - Market Permission)
"""

import asyncio
import os
import sys
import logging
from datetime import datetime
from typing import Optional
import json

from aiohttp import web
import pytz

# Add parent directory to path for contracts
project_root = os.path.join(os.path.dirname(__file__), '../../')
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from contracts.schemas import MarketState, StateChangeNotification, HealthCheck

try:
    from logic import RegimeCalculator
    from vol_proxy import VolatilityProxy
except ImportError:
    # Handle relative imports
    from .logic import RegimeCalculator
    from .vol_proxy import VolatilityProxy

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ET timezone
ET = pytz.timezone('America/New_York')


class RegimeService:
    """ZERO Regime Engine Service"""
    
    def __init__(self):
        self.calculator = RegimeCalculator()
        self.vol_proxy = VolatilityProxy(
            alpaca_api_key=os.getenv("ALPACA_API_KEY"),
            alpaca_secret_key=os.getenv("ALPACA_SECRET_KEY")
        )
        
        # Redis connection
        self.redis_host = os.getenv("REDIS_HOST", "redis")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_client = None
        
        # Database connection
        self.db_host = os.getenv("DB_HOST", "timescaledb")
        self.db_port = int(os.getenv("DB_PORT", "5432"))
        self.db_name = os.getenv("DB_NAME", "zero_trading")
        self.db_user = os.getenv("DB_USER", "zero_user")
        self.db_password = os.getenv("DB_PASSWORD")
        self.db_pool = None
        
        # State tracking
        self.last_state: Optional[MarketState] = None
        self.start_time = datetime.now(ET)
        self.running = False
        
        # HTTP server
        self.app = web.Application()
        self.app.router.add_get('/health', self.health_handler)
        self.runner = None
        self.site = None
    
    async def connect_redis(self):
        """Connect to Redis"""
        try:
            import redis.asyncio as aioredis
            self.redis_client = aioredis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                decode_responses=False
            )
            await self.redis_client.ping()
            logger.info(f"✅ Redis connected: {self.redis_host}:{self.redis_port}")
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            raise
    
    async def connect_db(self):
        """Connect to TimescaleDB"""
        try:
            import asyncpg
            self.db_pool = await asyncpg.create_pool(
                host=self.db_host,
                port=self.db_port,
                database=self.db_name,
                user=self.db_user,
                password=self.db_password,
                min_size=1,
                max_size=5
            )
            logger.info(f"✅ Database connected: {self.db_host}:{self.db_port}/{self.db_name}")
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            raise
    
    async def health_handler(self, request):
        """Health check endpoint"""
        try:
            current_state = self.last_state
            if current_state is None:
                status = "degraded"
                details = {"error": "No state calculated yet"}
            else:
                status = "healthy"
                details = {
                    "current_state": current_state.state,
                    "vix_level": current_state.vix_level,
                    "reason": current_state.reason
                }
            
            # Use UTC for timestamp (Pydantic expects UTC)
            from datetime import timezone
            last_update_utc = current_state.timestamp.astimezone(timezone.utc) if current_state else datetime.now(timezone.utc)
            
            health = HealthCheck(
                service="zero-regime",
                status=status,
                uptime_seconds=(datetime.now(ET) - self.start_time).total_seconds(),
                last_update=last_update_utc,
                details=details
            )
            
            return web.json_response(health.model_dump(mode='json'))
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return web.json_response(
                {"service": "zero-regime", "status": "unhealthy", "error": str(e)},
                status=500
            )
    
    async def calculate_and_publish_state(self):
        """Calculate market state and publish if changed"""
        try:
            # Get current time in ET
            now_et = datetime.now(ET)
            
            # Fetch volatility
            vix_level, vix_source = await self.vol_proxy.fetch_volatility()
            
            # Calculate market state
            state, reason = self.calculator.calculate_market_state(
                now_et=now_et,
                vix_level=vix_level,
                vix_source=vix_source,
                event_risk=False  # TODO: Add event calendar in future milestone
            )
            
            # Create MarketState object
            market_state = MarketState(
                state=state,
                vix_level=vix_level,
                vix_roc=None,  # TODO: Calculate in future
                adv_decl=None,  # TODO: Calculate in future
                trin=None,  # TODO: Calculate in future
                breadth_score=None,  # TODO: Calculate in future
                event_risk=False,
                reason=reason,
                timestamp=now_et
            )
            
            # Check if state changed
            state_changed = False
            if self.last_state is None:
                state_changed = True
            elif self.last_state.state != market_state.state:
                state_changed = True
            elif self.last_state.reason != market_state.reason:
                state_changed = True
            
            # Update last state
            self.last_state = market_state
            
            # If state changed, publish and persist
            if state_changed:
                logger.info(f"🔄 Market state changed: {state} - {reason}")
                
                # Write to Redis key
                await self.redis_client.set(
                    "key:market_state",
                    market_state.model_dump_json().encode('utf-8')
                )
                
                # Publish state change notification (NOT full state)
                notification = StateChangeNotification(
                    changed_fields=["state", "reason"] if self.last_state else ["state", "reason", "vix_level"],
                    state_key="key:market_state",
                    timestamp=now_et
                )
                await self.redis_client.publish(
                    "chan:market_state_changed",
                    notification.model_dump_json().encode('utf-8')
                )
                
                # Write to database
                async with self.db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO regime_log (
                            time, state, vix_level, vix_roc, adv_decl, trin,
                            breadth_score, event_risk, reason
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        """,
                        market_state.timestamp,
                        market_state.state,
                        market_state.vix_level,
                        market_state.vix_roc,
                        market_state.adv_decl,
                        market_state.trin,
                        market_state.breadth_score,
                        market_state.event_risk,
                        market_state.reason
                    )
                
                logger.info(f"✅ State published: {state} - {reason}")
            else:
                logger.debug(f"State unchanged: {state}")
            
        except Exception as e:
            logger.error(f"❌ Error calculating state: {e}", exc_info=True)
    
    async def run_loop(self):
        """Main service loop"""
        logger.info("🚀 ZERO Regime Engine starting...")
        
        # Connect to services
        await self.connect_redis()
        await self.connect_db()
        
        # Start HTTP server
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        port = int(os.getenv("REGIME_API_PORT", "8000"))
        self.site = web.TCPSite(self.runner, "0.0.0.0", port)
        await self.site.start()
        logger.info(f"✅ HTTP server started on port {port}")
        
        self.running = True
        
        # Initial state calculation
        await self.calculate_and_publish_state()
        
        # Main loop: update every 60 seconds
        while self.running:
            try:
                await asyncio.sleep(60)  # Wait 60 seconds
                await self.calculate_and_publish_state()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Loop error: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait before retry
    
    async def shutdown(self):
        """Shutdown service"""
        logger.info("🛑 Shutting down Regime Engine...")
        self.running = False
        
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        if self.redis_client:
            await self.redis_client.close()
        if self.db_pool:
            await self.db_pool.close()
        
        logger.info("✅ Shutdown complete")


async def main():
    """Main entry point"""
    service = RegimeService()
    
    try:
        await service.run_loop()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        await service.shutdown()


if __name__ == "__main__":
    asyncio.run(main())

