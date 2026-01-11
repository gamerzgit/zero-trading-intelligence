"""
Mock Market Data Provider (for testing/development)
"""

import asyncio
from typing import List, AsyncIterator
from datetime import datetime, timedelta
import random

from .base import MarketDataProvider, Candle


class MockProvider(MarketDataProvider):
    """Mock provider that generates fake candle data"""
    
    def __init__(self, symbols: List[str]):
        self.symbols = symbols
        self.connected = False
        self.base_prices = {
            "SPY": 450.0,
            "QQQ": 380.0,
            "IWM": 200.0,
            "AAPL": 180.0,
            "MSFT": 420.0,
        }
    
    async def connect(self) -> None:
        """Mock connection"""
        await asyncio.sleep(0.1)
        self.connected = True
    
    async def disconnect(self) -> None:
        """Mock disconnection"""
        self.connected = False
    
    async def stream_1m_candles(self, symbols: List[str]) -> AsyncIterator[Candle]:
        """Generate mock 1-minute candles"""
        if not self.connected:
            raise RuntimeError("Provider not connected")
        
        while True:
            now = datetime.utcnow()
            # Round down to nearest minute
            candle_time = now.replace(second=0, microsecond=0)
            
            for symbol in symbols:
                base_price = self.base_prices.get(symbol, 100.0)
                
                # Generate realistic price movement
                change = random.uniform(-0.5, 0.5)  # ±0.5% change
                open_price = base_price * (1 + change)
                high_price = open_price * (1 + random.uniform(0, 0.3))
                low_price = open_price * (1 - random.uniform(0, 0.3))
                close_price = random.uniform(low_price, high_price)
                volume = random.randint(100000, 1000000)
                
                # Update base price for next iteration
                self.base_prices[symbol] = close_price
                
                candle = Candle(
                    ticker=symbol,
                    time=candle_time,
                    open=round(open_price, 2),
                    high=round(high_price, 2),
                    low=round(low_price, 2),
                    close=round(close_price, 2),
                    volume=volume,
                    source="mock"
                )
                
                yield candle
            
            # Wait until next minute
            next_minute = candle_time + timedelta(minutes=1)
            wait_seconds = (next_minute - datetime.utcnow()).total_seconds()
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
    
    async def health_check(self) -> bool:
        """Check if provider is healthy"""
        return self.connected

