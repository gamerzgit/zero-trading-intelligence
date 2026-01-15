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
                logger.info("✅ Alpaca client initialized for VIXY fetching")
            except Exception as e:
                logger.warning(f"Failed to initialize Alpaca client: {e}")
        else:
            if not ALPACA_AVAILABLE:
                logger.warning("⚠️  alpaca-py not installed - VIXY fetching disabled")
            elif not alpaca_api_key or not alpaca_secret_key:
                logger.warning("⚠️  ALPACA_API_KEY or ALPACA_SECRET_KEY not set - VIXY fetching disabled")
    
    async def fetch_volatility(self) -> Tuple[Optional[float], Optional[float], str]:
        """
        Fetch volatility data from Alpaca API
        
        NOTE: VIX is an INDEX (CBOE Volatility Index), NOT a stock.
        Alpaca StockHistoricalDataClient only provides STOCKS, not indices.
        
        Strategy:
        1. Use VIXY ETF (tracks VIX futures) from Alpaca as volatility proxy
        2. Return VIXY price directly (do NOT convert to VIX - they are different)
        3. Thresholds are based on VIXY price levels, not VIX levels
        
        Returns:
            Tuple[Optional[float], Optional[float], str]: (vix_level, vixy_price, source_label)
            - vix_level: Real VIX level (None - not available from Alpaca Stock API)
            - vixy_price: VIXY ETF price (used for volatility thresholds)
            - source_label: "VIXY_ALPACA" or "UNAVAILABLE"
        """
        if not self.client:
            logger.info("⚠️  Alpaca client not available - skipping VIXY fetch")
            return None, None, "UNAVAILABLE"
        
        logger.info("📡 Fetching VIXY from Alpaca...")
        
        # VIX is an INDEX, not a stock - can't fetch directly from Alpaca Stock API
        # Use VIXY ETF which tracks VIX futures (available as a stock)
        # IMPORTANT: VIXY price is NOT VIX level - they are different instruments
        # NOTE: Must use date range, not limit=1, because limit=1 returns empty during off-hours
        try:
            end = datetime.now()
            start = end - timedelta(days=5)  # Look back 5 days to ensure we get data
            
            request = StockBarsRequest(
                symbol_or_symbols=['VIXY'],
                timeframe=TimeFrame.Day,
                start=start,
                end=end,
                feed='iex'  # Use IEX feed (free tier), not SIP
            )
            
            bars = self.client.get_stock_bars(request)
            
            # Access VIXY data - Alpaca returns BarSet with dict-like access
            bars_list = None
            try:
                bars_list = bars['VIXY']
            except (KeyError, TypeError):
                # Fallback methods
                if hasattr(bars, 'data') and 'VIXY' in bars.data:
                    bars_list = bars.data['VIXY']
            
            if bars_list and len(bars_list) >= 1:
                vixy_price = float(bars_list[-1].close)
                
                # Sanity check: VIXY should be $5-30 range typically
                if vixy_price < 1.0 or vixy_price > 50.0:
                    logger.warning(f"⚠️  VIXY price ${vixy_price:.2f} seems unusual - may be data error")
                
                # Return VIXY price as vixy_price (NOT as vix_level)
                # Real VIX is not available from Alpaca Stock API (it's an index, not a stock)
                # Thresholds in logic.py use VIXY price levels directly:
                #   GREEN: VIXY < $20
                #   YELLOW: VIXY $20-25
                #   RED: VIXY >= $25
                
                logger.info(f"✅ Fetched VIXY from Alpaca: ${vixy_price:.2f} (using VIXY-based thresholds, NOT VIX)")
                return None, vixy_price, "VIXY_ALPACA"  # vix_level=None, vixy_price=value
            
            logger.warning("⚠️  No VIXY bars found in response")
            return None, None, "UNAVAILABLE"
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch VIXY from Alpaca: {e}", exc_info=True)
            return None, None, "UNAVAILABLE"
    
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

