"""
ZERO Attention Engine Service - Milestone 8

Computes AttentionState (score-based 0-100) measuring market stability.
Publishes to Redis and persists to database.

Per SPEC_LOCK:
- STABLE: score >= 70
- UNSTABLE: score 40-69
- CHAOTIC: score < 40
"""

import asyncio
import os
import sys
import logging
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import asyncpg
import redis.asyncio as redis
from aiohttp import web

# Add project root to path
project_root = os.path.join(os.path.dirname(__file__), '../../')
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from db import AttentionDB
from logic import AttentionCalculator, INDEX_PROXIES, SECTOR_PROXIES, VOL_PROXY

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AttentionService:
    """
    ZERO Attention Engine Service
    
    Computes and publishes AttentionState every 60 seconds.
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
        self.api_port = int(os.getenv('ATTENTION_API_PORT', '8005'))
        
        # Update interval
        self.update_interval = int(os.getenv('ATTENTION_INTERVAL', '60'))
        
        # State
        self.db_pool: Optional[asyncpg.Pool] = None
        self.redis_client: Optional[redis.Redis] = None
        self.db: Optional[AttentionDB] = None
        self.calculator: Optional[AttentionCalculator] = None
        self.is_running = False
        self.current_state: Optional[Dict[str, Any]] = None
        self.last_update_time: Optional[datetime] = None
        self.start_time: Optional[datetime] = None
        
        # Symbols to track
        self.all_symbols = INDEX_PROXIES + SECTOR_PROXIES + [VOL_PROXY]
    
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
                max_size=5
            )
            self.db = AttentionDB(self.db_pool)
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
    
    async def load_market_state(self) -> str:
        """Load current market state from Redis"""
        try:
            state_json = await self.redis_client.get('key:market_state')
            if state_json:
                state = json.loads(state_json)
                return state.get('state', 'GREEN')
        except Exception as e:
            logger.warning(f"⚠️  Failed to load market state: {e}")
        return 'GREEN'  # Default
    
    async def compute_and_publish(self):
        """Compute attention state and publish to Redis/DB"""
        try:
            # Load market state for context
            market_state = await self.load_market_state()
            
            # Check available symbols
            available = await self.db.get_available_symbols(self.all_symbols)
            logger.info(f"📊 Available symbols: {len(available)}/{len(self.all_symbols)}")
            
            # Fetch recent candles (60 min lookback)
            all_candles = await self.db.get_recent_candles(
                symbols=available,
                minutes=90,  # Extra buffer
                table="candles_5m"
            )
            
            # Compute attention state
            attention_state = self.calculator.compute_attention_state(
                all_candles=all_candles,
                market_state=market_state
            )
            
            # Store current state
            self.current_state = attention_state
            self.last_update_time = datetime.now(timezone.utc)
            
            # Publish to Redis key
            await self.redis_client.set(
                'key:attention_state',
                json.dumps(attention_state)
            )
            
            # Publish change notification
            notification = {
                "schema_version": "1.0",
                "timestamp": attention_state["timestamp"],
                "changed_fields": ["attention_stability_score", "attention_bucket", "risk_on_off_state"],
                "state_key": "key:attention_state"
            }
            await self.redis_client.publish(
                'chan:attention_state_changed',
                json.dumps(notification)
            )
            
            # Persist to database
            log_id = await self.db.insert_attention_log(attention_state)
            
            logger.info(
                f"✅ Attention published: score={attention_state['attention_stability_score']}, "
                f"bucket={attention_state['attention_bucket']}, "
                f"risk={attention_state['risk_on_off_state']}, "
                f"db_id={log_id}"
            )
            
        except Exception as e:
            logger.error(f"❌ Error in compute_and_publish: {e}", exc_info=True)
            
            # Publish degraded state
            degraded = self.calculator._degraded_state(f"Service error: {str(e)}")
            self.current_state = degraded
            
            try:
                await self.redis_client.set(
                    'key:attention_state',
                    json.dumps(degraded)
                )
            except:
                pass
    
    async def run_loop(self):
        """Main computation loop"""
        logger.info(f"🔄 Starting attention loop (interval={self.update_interval}s)")
        
        while self.is_running:
            try:
                await self.compute_and_publish()
                await asyncio.sleep(self.update_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Loop error: {e}", exc_info=True)
                await asyncio.sleep(10)  # Brief pause before retry
    
    # HTTP Handlers
    async def health_handler(self, request):
        """Health check endpoint"""
        try:
            uptime = 0
            if self.start_time:
                uptime = (datetime.now(timezone.utc) - self.start_time).total_seconds()
            
            health = {
                "service": "zero-attention",
                "status": "healthy" if self.is_running else "starting",
                "uptime_seconds": uptime,
                "last_update": self.last_update_time.isoformat() if self.last_update_time else None,
                "current_state": {
                    "attention_stability_score": self.current_state.get("attention_stability_score") if self.current_state else None,
                    "attention_bucket": self.current_state.get("attention_bucket") if self.current_state else None,
                    "risk_on_off_state": self.current_state.get("risk_on_off_state") if self.current_state else None,
                    "correlation_regime": self.current_state.get("correlation_regime") if self.current_state else None
                } if self.current_state else None,
                "db_connected": self.db_pool is not None,
                "redis_connected": self.redis_client is not None
            }
            
            return web.json_response(health)
        except Exception as e:
            return web.json_response(
                {"service": "zero-attention", "status": "unhealthy", "error": str(e)},
                status=500
            )
    
    async def start(self):
        """Start the service"""
        self.is_running = True
        self.start_time = datetime.now(timezone.utc)
        
        # Initialize calculator
        self.calculator = AttentionCalculator()
        
        # Connect to services
        await self.connect_db()
        await self.connect_redis()
        
        # Setup HTTP server
        self.app = web.Application()
        self.app.router.add_get('/health', self.health_handler)
        
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, '0.0.0.0', self.api_port)
        await self.site.start()
        
        logger.info(f"✅ HTTP server started on port {self.api_port}")
        logger.info("🚀 ZERO Attention Engine started")
        
        # Start main loop
        await self.run_loop()
    
    async def stop(self):
        """Stop the service"""
        logger.info("🛑 Shutting down ZERO Attention Engine...")
        self.is_running = False
        
        if self.redis_client:
            await self.redis_client.aclose()
        if self.db_pool:
            await self.db_pool.close()
        if hasattr(self, 'site'):
            await self.site.stop()
        if hasattr(self, 'runner'):
            await self.runner.cleanup()
        
        logger.info("✅ ZERO Attention Engine stopped")


async def main():
    service = AttentionService()
    
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
