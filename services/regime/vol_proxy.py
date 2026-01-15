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
        
        NOTE: VIX is an INDEX (CBOE Volatility Index), NOT a stock.
        Alpaca StockHistoricalDataClient only provides STOCKS, not indices.
        
        Strategy:
        1. Use VIXY ETF (tracks VIX futures) from Alpaca
        2. Convert VIXY price to approximate VIX level using proper relationship
        3. VIXY is typically priced around $10-20 when VIX is 15-25
        4. Relationship: VIXY ≈ VIX / 10 (roughly, but varies with contango)
        
        Returns:
            Tuple[Optional[float], str]: (vix_level, source_label)
            - vix_level: Approximate VIX level derived from VIXY
            - source_label: "VIXY_ALPACA" or "UNAVAILABLE"
        """
        if not self.client:
            return None, "UNAVAILABLE"
        
        # VIX is an INDEX, not a stock - can't fetch directly from Alpaca Stock API
        # Use VIXY ETF which tracks VIX futures (available as a stock)
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
                
                # VIXY is a 1.5x leveraged ETF on VIX futures
                # Real relationship: VIXY typically trades roughly 1:1 with VIX in normal conditions
                # Examples:
                #   VIX = 15 → VIXY ≈ $10-15
                #   VIX = 20 → VIXY ≈ $15-20
                #   VIX = 25 → VIXY ≈ $20-25
                # 
                # The relationship is NOT linear and varies with contango/backwardation,
                # but for regime detection purposes, we can use: VIX ≈ VIXY (1:1)
                # 
                # Sanity check: VIXY should be $5-30 range typically
                if vixy_price < 1.0 or vixy_price > 50.0:
                    logger.warning(f"⚠️  VIXY price ${vixy_price:.2f} seems unusual - may be data error")
                
                # Return VIXY price directly (not converted to VIX)
                # Thresholds in logic.py are adjusted for VIXY price levels:
                #   GREEN: VIXY < $20
                #   YELLOW: VIXY $20-25
                #   RED: VIXY >= $25
                # This avoids conversion errors and makes the system more transparent
                
                logger.info(f"✅ Using VIXY from Alpaca: ${vixy_price:.2f} (using VIXY-based thresholds)")
                return vixy_price, "VIXY_ALPACA"
            
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

