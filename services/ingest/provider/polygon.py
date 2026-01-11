"""
Polygon.io Market Data Provider
"""

import asyncio
import aiohttp
from typing import List, AsyncIterator
from datetime import datetime, timedelta
import os

from .base import MarketDataProvider, Candle


class PolygonProvider(MarketDataProvider):
    """Polygon.io REST API provider"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.polygon.io"
        self.session: aiohttp.ClientSession = None
        self.connected = False
    
    async def connect(self) -> None:
        """Connect to Polygon API"""
        self.session = aiohttp.ClientSession()
        self.connected = True
    
    async def disconnect(self) -> None:
        """Disconnect from Polygon API"""
        if self.session:
            await self.session.close()
        self.connected = False
    
    async def stream_1m_candles(self, symbols: List[str]) -> AsyncIterator[Candle]:
        """Stream 1-minute candles via REST polling"""
        if not self.connected:
            raise RuntimeError("Provider not connected")
        
        while True:
            now = datetime.utcnow()
            # Round down to previous minute (Polygon aggregates with delay)
            candle_time = (now - timedelta(minutes=1)).replace(second=0, microsecond=0)
            
            for symbol in symbols:
                try:
                    # Get aggregates for previous minute
                    url = f"{self.base_url}/v2/aggs/ticker/{symbol}/range/1/minute/{candle_time.isoformat()}/{candle_time.isoformat()}"
                    params = {"adjusted": "true", "sort": "asc", "apiKey": self.api_key}
                    
                    async with self.session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            if data.get("resultsCount", 0) > 0:
                                result = data["results"][0]
                                
                                candle = Candle(
                                    ticker=symbol,
                                    time=datetime.fromtimestamp(result["t"] / 1000),
                                    open=result["o"],
                                    high=result["h"],
                                    low=result["l"],
                                    close=result["c"],
                                    volume=result["v"],
                                    source="polygon"
                                )
                                
                                yield candle
                        elif response.status == 429:
                            # Rate limit - wait and retry
                            await asyncio.sleep(60)
                        else:
                            # Log error but continue
                            print(f"Error fetching {symbol}: {response.status}")
                
                except Exception as e:
                    print(f"Error processing {symbol}: {e}")
                    # Continue with next symbol
            
            # Poll every minute
            await asyncio.sleep(60)
    
    async def health_check(self) -> bool:
        """Check if provider is healthy"""
        if not self.connected or not self.session:
            return False
        
        try:
            # Simple health check - test API key
            url = f"{self.base_url}/v2/aggs/ticker/SPY/range/1/day/2024-01-01/2024-01-01"
            params = {"apiKey": self.api_key}
            
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as response:
                return response.status in [200, 429]  # 429 means key works but rate limited
        except:
            return False

