"""
Market Data Provider Abstraction Layer
"""

from .base import MarketDataProvider, Candle
from .mock import MockProvider
from .polygon import PolygonProvider

# Alpaca provider (optional, requires alpaca-py)
try:
    from .alpaca import AlpacaProvider
    __all__ = ["MarketDataProvider", "Candle", "MockProvider", "PolygonProvider", "AlpacaProvider"]
except ImportError:
    __all__ = ["MarketDataProvider", "Candle", "MockProvider", "PolygonProvider"]

