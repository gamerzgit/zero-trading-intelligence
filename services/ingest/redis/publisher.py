"""
Redis Event Publisher for Market Data
"""

try:
    import redis.asyncio as aioredis
except ImportError:
    # Fallback for older redis versions
    import aioredis
import json
from typing import Optional
from datetime import datetime

from ..provider.base import Candle
from contracts.schemas import TickerUpdate, IndexUpdate, VolatilityUpdate


class RedisPublisher:
    """Publishes market data events to Redis Pub/Sub"""
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.client: Optional[aioredis.Redis] = None
    
    async def connect(self) -> None:
        """Connect to Redis"""
        self.client = aioredis.from_url(self.redis_url, decode_responses=False)
    
    async def disconnect(self) -> None:
        """Disconnect from Redis"""
        if self.client:
            await self.client.aclose()
    
    async def publish_ticker_update(self, candle: Candle) -> None:
        """Publish ticker update event"""
        update = TickerUpdate(
            ticker=candle.ticker,
            price=candle.close,
            volume=candle.volume,
            time=candle.time,
            bid=None,  # Not available from candles
            ask=None,
            spread=None
        )
        
        payload = update.model_dump_json()
        await self.client.publish("chan:ticker_update", payload.encode('utf-8'))
    
    async def publish_index_update(self, candle: Candle) -> None:
        """Publish index update (for SPY/QQQ/IWM)"""
        if candle.ticker not in ["SPY", "QQQ", "IWM"]:
            return
        
        update = IndexUpdate(
            index=candle.ticker,
            price=candle.close,
            volume=candle.volume,
            time=candle.time
        )
        
        payload = update.model_dump_json()
        await self.client.publish("chan:index_update", payload.encode('utf-8'))
    
    async def publish_volatility_update(self, vix_level: float, vix_roc: Optional[float] = None) -> None:
        """Publish volatility update (placeholder for now)"""
        # TODO: Implement VIX data fetching in future milestone
        update = VolatilityUpdate(
            vix_level=vix_level,
            vix_roc=vix_roc,
            time=datetime.utcnow()
        )
        
        payload = update.model_dump_json()
        await self.client.publish("chan:volatility_update", payload.encode('utf-8'))

