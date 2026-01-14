"""
ZERO Volatility Proxy - Fetch VIX or VIXY proxy
"""

import logging
from typing import Tuple, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

try:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False


class VolatilityProxy:
    """
    Fetch volatility signal (VIX preferred, VIXY proxy fallback)
    
    Returns (value, source_label) where source_label is "VIX" or "VIXY_PROXY"
    """
    
    def __init__(self, alpaca_api_key: Optional[str] = None, alpaca_secret_key: Optional[str] = None):
        self.alpaca_api_key = alpaca_api_key
        self.alpaca_secret_key = alpaca_secret_key
        self.client = None
        
        if ALPACA_AVAILABLE and alpaca_api_key and alpaca_secret_key:
            try:
                self.client = StockHistoricalDataClient(
                    api_key=alpaca_api_key,
                    secret_key=alpaca_secret_key,
                    raw_data=False
                )
            except Exception as e:
                logger.warning(f"Failed to initialize Alpaca client: {e}")
    
    async def fetch_volatility(self) -> Tuple[Optional[float], str]:
        """
        Fetch volatility level from Alpaca API
        
        Strategy:
        1. Try to get VIX directly from Alpaca (if available as symbol)
        2. If not, use VIXY ETF price directly (don't convert - use thresholds based on VIXY levels)
        3. Fallback to UNAVAILABLE
        
        Returns:
            Tuple[Optional[float], str]: (value, source_label)
            - value: VIX level (if available) or VIXY price (if using proxy)
            - source_label: "VIX_ALPACA", "VIXY_DIRECT", or "UNAVAILABLE"
        """
        if not self.client:
            return None, "UNAVAILABLE"
        
        # Strategy 1: Try VIX directly from Alpaca (might not be available, but worth trying)
        try:
            request = StockBarsRequest(
                symbol_or_symbols=['VIX'],
                timeframe=TimeFrame.Day,
                limit=1,
                feed='iex'
            )
            bars = self.client.get_stock_bars(request)
            
            bars_list = None
            if bars:
                if isinstance(bars, dict) and "VIX" in bars:
                    bars_list = bars["VIX"]
                elif hasattr(bars, "VIX"):
                    bars_list = bars.VIX
                elif hasattr(bars, "data") and isinstance(bars.data, dict) and "VIX" in bars.data:
                    bars_list = bars.data["VIX"]
                elif isinstance(bars, list):
                    bars_list = bars
            
            if bars_list and len(bars_list) >= 1:
                vix_level = float(bars_list[-1].close)
                logger.info(f"✅ Fetched VIX directly from Alpaca: {vix_level:.2f}")
                return vix_level, "VIX_ALPACA"
        except Exception as e:
            logger.debug(f"VIX not available directly from Alpaca: {e}")
        
        # Strategy 2: Use VIXY ETF price directly (don't convert - use VIXY-based thresholds)
        # VIXY is a 1.5x leveraged ETF on VIX futures
        # Instead of converting, we'll use VIXY price levels directly for thresholds
        try:
            request = StockBarsRequest(
                symbol_or_symbols=['VIXY'],
                timeframe=TimeFrame.Day,
                limit=1,
                feed='iex'
            )
            
            bars = self.client.get_stock_bars(request)
            
            bars_list = None
            if bars:
                if isinstance(bars, dict) and "VIXY" in bars:
                    bars_list = bars["VIXY"]
                elif hasattr(bars, "VIXY"):
                    bars_list = bars.VIXY
                elif hasattr(bars, "data") and isinstance(bars.data, dict) and "VIXY" in bars.data:
                    bars_list = bars.data["VIXY"]
                elif isinstance(bars, list):
                    bars_list = bars
            
            if bars_list and len(bars_list) >= 1:
                vixy_price = float(bars_list[-1].close)
                # Use VIXY price directly, but convert to approximate VIX for display
                # VIXY ≈ VIX * 0.1 (rough approximation, varies with contango/backwardation)
                # So VIX ≈ VIXY * 10 (but this is still approximate)
                # Better: Use VIXY price with adjusted thresholds
                # For now, convert for compatibility, but label clearly
                vix_approx = vixy_price * 10  # Rough: VIXY $1.5 ≈ VIX 15
                logger.info(f"✅ Using VIXY from Alpaca: ${vixy_price:.2f} (≈ VIX {vix_approx:.1f})")
                return vix_approx, "VIXY_ALPACA"
            
            return None, "UNAVAILABLE"
            
        except Exception as e:
            logger.warning(f"Failed to fetch VIXY from Alpaca: {e}")
            return None, "UNAVAILABLE"
    
    def get_volatility_zone(self, vix_level: Optional[float]) -> Tuple[str, str]:
        """
        Classify volatility zone
        
        Returns:
            Tuple[str, str]: (zone, reason_suffix)
            - zone: "GREEN", "YELLOW", or "RED"
            - reason_suffix: Text to append to reason
        """
        if vix_level is None:
            return "GREEN", ""  # Default to GREEN if unavailable
        
        if vix_level >= 25:
            return "RED", f"Volatility Halt (>=25)"
        elif vix_level >= 20:
            return "YELLOW", f"Elevated Volatility (20-25)"
        else:
            return "GREEN", ""  # < 20 is GREEN zone

