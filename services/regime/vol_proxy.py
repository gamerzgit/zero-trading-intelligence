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
        Fetch volatility level
        
        Returns:
            Tuple[Optional[float], str]: (value, source_label)
            - value: VIX level or VIXY-based estimate, or None if unavailable
            - source_label: "VIX" or "VIXY_PROXY" or "UNAVAILABLE"
        """
        # Try real VIX first (if provider supports it)
        # For now, we'll use VIXY proxy as primary method
        # Future: Add real VIX provider when available
        
        if not self.client:
            return None, "UNAVAILABLE"
        
        try:
            # Use VIXY ETF as proxy
            request = StockBarsRequest(
                symbol_or_symbols='VIXY',
                timeframe=TimeFrame.Day,
                limit=2,
                feed='iex'
            )
            
            bars = self.client.get_stock_bars(request)
            
            # Handle different response structures
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
                current = float(bars_list[-1].close)
                
                # Estimate VIX from VIXY
                # VIXY ~$10-15 normally, spikes to $20+ in fear
                # Rough conversion: VIXY $10 ≈ VIX 15, VIXY $15 ≈ VIX 25
                vix_estimate = (current / 10) * 15
                
                logger.debug(f"VIX Proxy (VIXY): {current:.2f} → VIX estimate: {vix_estimate:.1f}")
                return float(vix_estimate), "VIXY_PROXY"
            
            return None, "UNAVAILABLE"
            
        except Exception as e:
            logger.warning(f"Failed to fetch VIXY proxy: {e}")
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

