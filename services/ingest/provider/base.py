"""
Base Provider Interface for Market Data
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, List
from datetime import datetime
from dataclasses import dataclass


@dataclass
class Candle:
    """1-minute OHLCV candle"""
    ticker: str
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    source: str = "unknown"


class MarketDataProvider(ABC):
    """Abstract base class for market data providers"""
    
    @abstractmethod
    async def connect(self) -> None:
        """Connect to data provider"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from data provider"""
        pass
    
    @abstractmethod
    async def stream_1m_candles(self, symbols: List[str]) -> AsyncIterator[Candle]:
        """
        Stream 1-minute candles for given symbols
        
        Args:
            symbols: List of ticker symbols (e.g., ["SPY", "AAPL"])
            
        Yields:
            Candle objects as they arrive
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if provider is healthy and connected"""
        pass

