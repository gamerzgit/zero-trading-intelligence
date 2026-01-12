"""
ZERO Scanner - Filter Logic
Filters universe to find Active Candidates
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class ScannerFilters:
    """Filter logic for candidate discovery"""
    
    def __init__(self):
        # Filter thresholds (configurable)
        self.min_volume_ratio = 1.5  # Relative volume must be >= 1.5x average
        self.min_atr_pct = 0.01  # ATR must be >= 1% of price (volatility filter)
        self.min_price = 5.0  # Minimum price (avoid penny stocks)
        self.max_price = 10000.0  # Maximum price (avoid splits/errors)
        self.min_avg_volume = 100000  # Minimum average daily volume
        
    def filter_liquidity(
        self, 
        ticker: str, 
        candles_1m: pd.DataFrame,
        candles_5m: pd.DataFrame
    ) -> tuple[bool, Dict[str, Any]]:
        """
        Filter based on liquidity criteria
        
        Returns:
            (passed, stats_dict)
        """
        if candles_1m.empty and candles_5m.empty:
            return False, {"reason": "No data available"}
        
        # Use 5m candles if available, else 1m
        df = candles_5m if not candles_5m.empty else candles_1m
        
        if len(df) < 10:
            return False, {"reason": "Insufficient data points"}
        
        # Calculate average volume
        avg_volume = df['volume'].mean()
        
        # Check minimum volume threshold
        if avg_volume < self.min_avg_volume:
            return False, {
                "reason": f"Low average volume: {avg_volume:.0f}",
                "avg_volume": avg_volume
            }
        
        # Calculate relative volume (current vs average)
        if len(df) > 0:
            recent_volume = df['volume'].tail(5).mean()
            relative_volume = recent_volume / avg_volume if avg_volume > 0 else 0
            
            if relative_volume < self.min_volume_ratio:
                return False, {
                    "reason": f"Low relative volume: {relative_volume:.2f}x",
                    "relative_volume": relative_volume,
                    "avg_volume": avg_volume
                }
        else:
            relative_volume = 0
        
        return True, {
            "avg_volume": avg_volume,
            "relative_volume": relative_volume,
            "passed": True
        }
    
    def filter_volatility(
        self,
        ticker: str,
        candles_1m: pd.DataFrame,
        candles_5m: pd.DataFrame
    ) -> tuple[bool, Dict[str, Any]]:
        """
        Filter based on volatility (ATR) criteria
        
        Returns:
            (passed, stats_dict)
        """
        if candles_1m.empty and candles_5m.empty:
            return False, {"reason": "No data available"}
        
        # Use 5m candles if available, else 1m
        df = candles_5m if not candles_5m.empty else candles_1m
        
        if len(df) < 14:  # Need at least 14 periods for ATR
            return False, {"reason": "Insufficient data for ATR calculation"}
        
        # Calculate ATR (simplified - using high-low range)
        high_low = df['high'] - df['low']
        atr = high_low.rolling(window=14, min_periods=1).mean().iloc[-1]
        
        # Get current price
        current_price = df['close'].iloc[-1]
        
        # Check price bounds
        if current_price < self.min_price or current_price > self.max_price:
            return False, {
                "reason": f"Price out of bounds: ${current_price:.2f}",
                "price": current_price
            }
        
        # Calculate ATR as percentage of price
        atr_pct = (atr / current_price) if current_price > 0 else 0
        
        if atr_pct < self.min_atr_pct:
            return False, {
                "reason": f"Low volatility (ATR): {atr_pct:.4f}",
                "atr": atr,
                "atr_pct": atr_pct,
                "price": current_price
            }
        
        return True, {
            "atr": float(atr),
            "atr_pct": float(atr_pct),
            "price": float(current_price),
            "passed": True
        }
    
    def filter_structure(
        self,
        ticker: str,
        candles_1m: pd.DataFrame,
        candles_5m: pd.DataFrame
    ) -> tuple[bool, Dict[str, Any]]:
        """
        Filter based on structure/pattern (placeholder for future pattern recognition)
        
        Currently: Basic structure check (trend direction, consolidation)
        Future: Pattern recognition (Bull Flag, Hammer, etc.)
        
        Returns:
            (passed, stats_dict)
        """
        if candles_1m.empty and candles_5m.empty:
            return False, {"reason": "No data available"}
        
        # Use 5m candles if available, else 1m
        df = candles_5m if not candles_5m.empty else candles_1m
        
        if len(df) < 20:
            return False, {"reason": "Insufficient data for structure analysis"}
        
        # Basic structure checks
        # 1. Check for trend (simple moving average)
        sma_short = df['close'].rolling(window=9).mean()
        sma_long = df['close'].rolling(window=21).mean()
        
        if len(sma_short) < 1 or len(sma_long) < 1:
            return False, {"reason": "Cannot calculate trend"}
        
        # Determine trend direction
        current_price = df['close'].iloc[-1]
        trend_up = current_price > sma_short.iloc[-1] > sma_long.iloc[-1]
        trend_down = current_price < sma_short.iloc[-1] < sma_long.iloc[-1]
        
        # For now, accept any clear trend (up or down)
        # Future: Add pattern recognition here
        has_structure = trend_up or trend_down
        
        if not has_structure:
            return False, {
                "reason": "No clear structure/trend",
                "trend": "CHOP"
            }
        
        return True, {
            "trend": "UP" if trend_up else "DOWN",
            "pattern": "PLACEHOLDER",  # Future: "BULL_FLAG", "HAMMER", etc.
            "passed": True
        }
    
    def apply_all_filters(
        self,
        ticker: str,
        candles_1m: pd.DataFrame,
        candles_5m: pd.DataFrame
    ) -> tuple[bool, Dict[str, Any]]:
        """
        Apply all filters and return combined result
        
        Returns:
            (passed, combined_stats_dict)
        """
        # Apply liquidity filter
        liquidity_passed, liquidity_stats = self.filter_liquidity(ticker, candles_1m, candles_5m)
        if not liquidity_passed:
            return False, {
                "filter": "liquidity",
                **liquidity_stats
            }
        
        # Apply volatility filter
        volatility_passed, volatility_stats = self.filter_volatility(ticker, candles_1m, candles_5m)
        if not volatility_passed:
            return False, {
                "filter": "volatility",
                **volatility_stats
            }
        
        # Apply structure filter
        structure_passed, structure_stats = self.filter_structure(ticker, candles_1m, candles_5m)
        if not structure_passed:
            return False, {
                "filter": "structure",
                **structure_stats
            }
        
        # All filters passed
        return True, {
            "liquidity": liquidity_stats,
            "volatility": volatility_stats,
            "structure": structure_stats,
            "passed_all": True
        }

