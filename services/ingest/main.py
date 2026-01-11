"""
ZERO Price Ingestion Service
Milestone 1: Pure ingestion + persistence
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from typing import List
import logging
from aiohttp import web
import json

# Add parent directory to path for contracts
project_root = os.path.join(os.path.dirname(__file__), '../../')
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from provider import MarketDataProvider, MockProvider, PolygonProvider
from db import DatabaseWriter
from redis import RedisPublisher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IngestionService:
    """Main ingestion service"""
    
    def __init__(self):
        self.provider: MarketDataProvider = None
        self.db_writer: DatabaseWriter = None
        self.redis_pub: RedisPublisher = None
        self.running = False
        self.symbols = ["SPY", "QQQ", "IWM", "AAPL", "MSFT"]
        self.start_time = None
        
        # Configuration
        self.provider_type = os.getenv("PROVIDER_TYPE", "mock").lower()
        self.db_url = os.getenv(
            "DB_URL",
            f"postgresql://{os.getenv('DB_USER', 'zero_user')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST', 'timescaledb')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'zero_trading')}"
        )
        self.redis_url = os.getenv(
            "REDIS_URL",
            f"redis://{os.getenv('REDIS_HOST', 'redis')}:{os.getenv('REDIS_PORT', '6379')}"
        )
    
    async def initialize(self) -> None:
        """Initialize all components"""
        logger.info("Initializing ingestion service...")
        
        # Initialize provider
        if self.provider_type == "polygon":
            api_key = os.getenv("POLYGON_API_KEY")
            if not api_key:
                raise ValueError("POLYGON_API_KEY required for polygon provider")
            self.provider = PolygonProvider(api_key)
        elif self.provider_type == "alpaca":
            api_key = os.getenv("ALPACA_API_KEY")
            secret_key = os.getenv("ALPACA_SECRET_KEY")
            paper = os.getenv("ALPACA_PAPER", "true").lower() == "true"
            if not api_key or not secret_key:
                raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY required for alpaca provider")
            try:
                from provider import AlpacaProvider
                self.provider = AlpacaProvider(api_key, secret_key, paper)
            except ImportError:
                raise ImportError("alpaca-py not installed. Install with: pip install alpaca-py")
        else:
            self.provider = MockProvider(self.symbols)
        
        await self.provider.connect()
        logger.info(f"Provider connected: {self.provider_type}")
        
        # Initialize database writer
        self.db_writer = DatabaseWriter(self.db_url)
        await self.db_writer.connect()
        logger.info("Database connected")
        
        # Initialize Redis publisher
        self.redis_pub = RedisPublisher(self.redis_url)
        await self.redis_pub.connect()
        logger.info("Redis connected")
        
        self.start_time = datetime.utcnow()
        logger.info("Initialization complete")
    
    async def shutdown(self) -> None:
        """Shutdown all components"""
        logger.info("Shutting down...")
        self.running = False
        
        if self.provider:
            await self.provider.disconnect()
        if self.db_writer:
            await self.db_writer.disconnect()
        if self.redis_pub:
            await self.redis_pub.disconnect()
        
        logger.info("Shutdown complete")
    
    async def ingest_loop(self) -> None:
        """Main ingestion loop"""
        logger.info(f"Starting ingestion for symbols: {self.symbols}")
        self.running = True
        
        last_5m_agg = {}
        last_1d_agg = {}
        
        try:
            async for candle in self.provider.stream_1m_candles(self.symbols):
                if not self.running:
                    break
                
                try:
                    # Write 1-minute candle
                    await self.db_writer.write_1m_candle(candle)
                    
                    # Detect gaps
                    await self.db_writer.detect_gaps(candle.ticker, candle.time)
                    
                    # Publish Redis events
                    await self.redis_pub.publish_ticker_update(candle)
                    await self.redis_pub.publish_index_update(candle)
                    
                    # Aggregate to 5-minute (every 5 minutes)
                    candle_minute = candle.time.minute
                    if candle_minute % 5 == 0:
                        last_5m_time = last_5m_agg.get(candle.ticker)
                        if not last_5m_time or candle.time > last_5m_time + timedelta(minutes=5):
                            from_time = candle.time - timedelta(minutes=5)
                            await self.db_writer.aggregate_5m_candles(
                                candle.ticker, from_time, candle.time
                            )
                            last_5m_agg[candle.ticker] = candle.time
                    
                    # Aggregate to daily (at start of new day)
                    candle_date = candle.time.date()
                    last_1d_date = last_1d_agg.get(candle.ticker)
                    if not last_1d_date or candle_date > last_1d_date:
                        await self.db_writer.aggregate_1d_candles(candle.ticker, candle.time)
                        last_1d_agg[candle.ticker] = candle_date
                    
                    logger.debug(f"Ingested {candle.ticker} @ {candle.time}")
                
                except Exception as e:
                    logger.error(f"Error processing candle for {candle.ticker}: {e}", exc_info=True)
                    # Continue with next candle
        
        except Exception as e:
            logger.error(f"Fatal error in ingestion loop: {e}", exc_info=True)
            raise
    
    async def health_check(self) -> dict:
        """Get health status"""
        health = {
            "service": "zero-ingest-price",
            "status": "healthy" if self.running else "unhealthy",
            "uptime_seconds": (datetime.utcnow() - self.start_time).total_seconds() if self.start_time else 0,
            "last_update": datetime.utcnow().isoformat(),
            "details": {}
        }
        
        # Check provider
        try:
            provider_healthy = await self.provider.health_check() if self.provider else False
            health["details"]["provider_connected"] = provider_healthy
            health["details"]["provider_type"] = self.provider_type
        except Exception as e:
            health["details"]["provider_error"] = str(e)
            health["status"] = "degraded"
        
        # Check database
        try:
            if self.db_writer and self.db_writer.pool:
                async with self.db_writer.pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                health["details"]["database_connected"] = True
            else:
                health["details"]["database_connected"] = False
                health["status"] = "unhealthy"
        except Exception as e:
            health["details"]["database_error"] = str(e)
            health["status"] = "unhealthy"
        
        # Check Redis
        try:
            if self.redis_pub and self.redis_pub.client:
                await self.redis_pub.client.ping()
                health["details"]["redis_connected"] = True
            else:
                health["details"]["redis_connected"] = False
                health["status"] = "degraded"
        except Exception as e:
            health["details"]["redis_error"] = str(e)
            health["status"] = "degraded"
        
        # Get last candle times
        if self.db_writer:
            health["details"]["last_candles"] = {}
            for symbol in self.symbols:
                try:
                    last_time = await self.db_writer.get_last_candle_time(symbol)
                    count = await self.db_writer.get_candle_count(symbol)
                    health["details"]["last_candles"][symbol] = {
                        "last_time": last_time.isoformat() if last_time else None,
                        "count": count
                    }
                except Exception as e:
                    health["details"]["last_candles"][symbol] = {"error": str(e)}
        
        return health


# HTTP Server for health checks
async def health_handler(request):
    """Health check endpoint"""
    service = request.app["service"]
    health = await service.health_check()
    
    status_code = 200 if health["status"] == "healthy" else 503
    return web.json_response(health, status=status_code)


async def init_app(service: IngestionService):
    """Initialize HTTP app"""
    app = web.Application()
    app["service"] = service
    app.router.add_get("/health", health_handler)
    return app


async def main():
    """Main entry point"""
    service = IngestionService()
    
    try:
        # Initialize
        await service.initialize()
        
        # Start HTTP server
        app = await init_app(service)
        runner = web.AppRunner(app)
        await runner.setup()
        
        port = int(os.getenv("API_PORT", "8080"))
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Health endpoint listening on port {port}")
        
        # Start ingestion loop
        await service.ingest_loop()
    
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await service.shutdown()


if __name__ == "__main__":
    asyncio.run(main())

