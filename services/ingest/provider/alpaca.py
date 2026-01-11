"""
Alpaca Market Data Provider
"""

import asyncio
from typing import List, AsyncIterator
from datetime import datetime, timedelta
import os

from .base import MarketDataProvider, Candle

try:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False


class AlpacaProvider(MarketDataProvider):
    """Alpaca API provider for market data"""
    
    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        if not ALPACA_AVAILABLE:
            raise ImportError("alpaca-py not installed. Install with: pip install alpaca-py")
        
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper
        self.client: StockHistoricalDataClient = None
        self.connected = False
        self.last_fetch_time: dict[str, datetime] = {}
    
    async def connect(self) -> None:
        """Connect to Alpaca API"""
        self.client = StockHistoricalDataClient(
            api_key=self.api_key,
            secret_key=self.secret_key,
            raw_data=False
        )
        self.connected = True
    
    async def disconnect(self) -> None:
        """Disconnect from Alpaca API"""
        self.connected = False
        # Alpaca client doesn't need explicit close
    
    async def stream_1m_candles(self, symbols: List[str]) -> AsyncIterator[Candle]:
        """Stream 1-minute candles via REST polling"""
        if not self.connected:
            raise RuntimeError("Provider not connected")
        
        while True:
            now = datetime.utcnow()
            # Round down to previous minute (Alpaca aggregates with delay)
            candle_time = (now - timedelta(minutes=1)).replace(second=0, microsecond=0)
            
            for symbol in symbols:
                try:
                    # Determine fetch window (last 2 minutes to catch any missed candles)
                    fetch_start = candle_time - timedelta(minutes=2)
                    fetch_end = candle_time + timedelta(minutes=1)
                    
                    request = StockBarsRequest(
                        symbol_or_symbols=[symbol],
                        timeframe=TimeFrame.Minute,
                        start=fetch_start,
                        end=fetch_end,
                        feed='iex'  # Use free IEX feed (no SIP subscription required)
                    )
                    
                    bars = self.client.get_stock_bars(request)
                    
                    if bars and symbol in bars:
                        for bar in bars[symbol]:
                            # Only yield if we haven't seen this bar before
                            bar_time = bar.timestamp.replace(tzinfo=None) if bar.timestamp.tzinfo else bar.timestamp
                            
                            if symbol not in self.last_fetch_time or bar_time > self.last_fetch_time.get(symbol, datetime.min):
                                candle = Candle(
                                    ticker=symbol,
                                    time=bar_time,
                                    open=float(bar.open),
                                    high=float(bar.high),
                                    low=float(bar.low),
                                    close=float(bar.close),
                                    volume=int(bar.volume),
                                    source="alpaca"
                                )
                                
                                self.last_fetch_time[symbol] = bar_time
                                yield candle
                
                except Exception as e:
                    print(f"Error fetching {symbol} from Alpaca: {e}")
                    # Continue with next symbol
            
            # Poll every minute
            await asyncio.sleep(60)
    
    async def health_check(self) -> bool:
        """Check if provider is healthy"""
        if not self.connected or not self.client:
            return False
        
        try:
            # Simple health check - try to fetch recent data for SPY
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=1)
            
            request = StockBarsRequest(
                symbol_or_symbols=["SPY"],
                timeframe=TimeFrame.Minute,
                start=start_time,
                end=end_time
            )
            
            bars = self.client.get_stock_bars(request)
            return bars is not None
        except:
            return False

