"""
ZERO Core Logic - Feature Engineering
Calculates features from 1m, 5m, and optionally 1d candles
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


def calculate_ema(prices: pd.Series, period: int) -> pd.Series:
    """Calculate Exponential Moving Average"""
    return prices.ewm(span=period, adjust=False).mean()


def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Average True Range"""
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def calculate_ema_alignment(close: pd.Series) -> Tuple[bool, float]:
    """
    Check EMA alignment: Price > EMA9 > EMA20
    Returns: (is_aligned, separation_pct)
    """
    if len(close) < 20:
        return False, 0.0
    
    ema9 = calculate_ema(close, 9)
    ema20 = calculate_ema(close, 20)
    
    latest_price = close.iloc[-1]
    latest_ema9 = ema9.iloc[-1]
    latest_ema20 = ema20.iloc[-1]
    
    is_aligned = latest_price > latest_ema9 > latest_ema20
    
    # Calculate separation percentage
    if latest_ema20 > 0:
        separation_pct = ((latest_ema9 - latest_ema20) / latest_ema20) * 100
    else:
        separation_pct = 0.0
    
    return is_aligned, separation_pct


def calculate_ema_slope(ema: pd.Series, periods: int = 5) -> float:
    """Calculate EMA slope (rate of change)"""
    if len(ema) < periods + 1:
        return 0.0
    
    recent = ema.iloc[-periods:]
    slope = (recent.iloc[-1] - recent.iloc[0]) / recent.iloc[0] * 100
    return float(slope)


def calculate_atr_level(high: pd.Series, low: pd.Series, close: pd.Series) -> Tuple[float, float]:
    """
    Calculate ATR level and ATR expansion
    Returns: (atr_value, atr_expansion_pct)
    """
    if len(close) < 20:
        return 0.0, 0.0
    
    atr = calculate_atr(high, low, close, period=14)
    latest_atr = atr.iloc[-1]
    
    # Calculate ATR expansion (change over last 5 periods)
    if len(atr) >= 6:
        atr_expansion = ((latest_atr - atr.iloc[-6]) / atr.iloc[-6]) * 100
    else:
        atr_expansion = 0.0
    
    return float(latest_atr), float(atr_expansion)


def calculate_relative_volume(volume: pd.Series, lookback_periods: int = 20) -> float:
    """Calculate relative volume (current vs average)"""
    if len(volume) < lookback_periods:
        return 1.0
    
    current_volume = volume.iloc[-1]
    avg_volume = volume.iloc[-lookback_periods:].mean()
    
    if avg_volume > 0:
        rel_vol = current_volume / avg_volume
    else:
        rel_vol = 1.0
    
    return float(rel_vol)


def calculate_stability_divergence(candles_1m: pd.DataFrame, candles_5m: pd.DataFrame) -> float:
    """
    Calculate stability by comparing 1m vs 5m trends
    Returns divergence score (lower = more stable)
    """
    if len(candles_1m) < 10 or len(candles_5m) < 5:
        return 0.0
    
    # Get recent close prices
    close_1m = candles_1m['close'].iloc[-10:]
    close_5m = candles_5m['close'].iloc[-5:]
    
    # Calculate slopes
    slope_1m = (close_1m.iloc[-1] - close_1m.iloc[0]) / close_1m.iloc[0] * 100
    slope_5m = (close_5m.iloc[-1] - close_5m.iloc[0]) / close_5m.iloc[0] * 100
    
    # Divergence = absolute difference
    divergence = abs(slope_1m - slope_5m)
    
    return float(divergence)


def extract_features(
    candles_1m: pd.DataFrame,
    candles_5m: pd.DataFrame,
    candles_1d: Optional[pd.DataFrame] = None
) -> Dict[str, Any]:
    """
    Extract all features from candles
    
    Args:
        candles_1m: 1-minute candles DataFrame
        candles_5m: 5-minute candles DataFrame
        candles_1d: Optional daily candles DataFrame (for swing horizons)
    
    Returns:
        Dict with feature values
    """
    features = {}
    
    # 1m features
    if len(candles_1m) >= 20:
        close_1m = candles_1m['close']
        features['ema_aligned_1m'], features['ema_separation_1m'] = calculate_ema_alignment(close_1m)
        features['ema9_slope_1m'] = calculate_ema_slope(calculate_ema(close_1m, 9))
        features['rel_volume_1m'] = calculate_relative_volume(candles_1m['volume'])
        features['current_price'] = float(close_1m.iloc[-1])
        
        # VWAP calculation for direction detection
        typical_price = (candles_1m['high'] + candles_1m['low'] + candles_1m['close']) / 3
        cumulative_tp_vol = (typical_price * candles_1m['volume']).cumsum()
        cumulative_vol = candles_1m['volume'].cumsum()
        vwap = cumulative_tp_vol / cumulative_vol
        features['vwap'] = float(vwap.iloc[-1]) if cumulative_vol.iloc[-1] > 0 else 0.0
        
        # Recent return for direction
        if len(close_1m) >= 5:
            features['recent_return_1m'] = float((close_1m.iloc[-1] / close_1m.iloc[-5] - 1) * 100)
        else:
            features['recent_return_1m'] = 0.0
    else:
        features['ema_aligned_1m'] = False
        features['ema_separation_1m'] = 0.0
        features['ema9_slope_1m'] = 0.0
        features['rel_volume_1m'] = 1.0
        features['current_price'] = 0.0
        features['vwap'] = 0.0
        features['recent_return_1m'] = 0.0
    
    # 5m features
    if len(candles_5m) >= 20:
        close_5m = candles_5m['close']
        features['ema_aligned_5m'], features['ema_separation_5m'] = calculate_ema_alignment(close_5m)
        features['ema9_slope_5m'] = calculate_ema_slope(calculate_ema(close_5m, 9))
        features['atr_5m'], features['atr_expansion_5m'] = calculate_atr_level(
            candles_5m['high'], candles_5m['low'], close_5m
        )
        features['rel_volume_5m'] = calculate_relative_volume(candles_5m['volume'])
        
        # Recent return for direction (5m timeframe)
        if len(close_5m) >= 5:
            features['recent_return_5m'] = float((close_5m.iloc[-1] / close_5m.iloc[-5] - 1) * 100)
        else:
            features['recent_return_5m'] = 0.0
    else:
        features['ema_aligned_5m'] = False
        features['ema_separation_5m'] = 0.0
        features['ema9_slope_5m'] = 0.0
        features['atr_5m'] = 0.0
        features['atr_expansion_5m'] = 0.0
        features['rel_volume_5m'] = 1.0
        features['recent_return_5m'] = 0.0
    
    # Stability (1m vs 5m divergence)
    if len(candles_1m) >= 10 and len(candles_5m) >= 5:
        features['stability_divergence'] = calculate_stability_divergence(candles_1m, candles_5m)
    else:
        features['stability_divergence'] = 0.0
    
    # 1d features (for swing horizons)
    if candles_1d is not None and len(candles_1d) >= 20:
        close_1d = candles_1d['close']
        features['ema_aligned_1d'], features['ema_separation_1d'] = calculate_ema_alignment(close_1d)
    else:
        features['ema_aligned_1d'] = False
        features['ema_separation_1d'] = 0.0
    
    return features
