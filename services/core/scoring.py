"""
ZERO Core Logic - Scoring Engine
Calculates opportunity scores (0-100) based on momentum, volatility, liquidity, and stability
Uses penalties (not bonuses) for MarketState adjustments
Includes direction detection (LONG/SHORT/NEUTRAL)
"""

from typing import Dict, Any, Literal, Tuple
import logging

logger = logging.getLogger(__name__)

# Direction type
Direction = Literal["LONG", "SHORT", "NEUTRAL"]


def score_momentum(features: Dict[str, Any]) -> float:
    """
    Score momentum based on EMA alignment and slope (1m + 5m)
    Returns 0-100 score
    """
    score = 0.0
    
    # 1m momentum (40% weight)
    if features.get('ema_aligned_1m', False):
        score += 40.0
        # Bonus for separation
        separation = features.get('ema_separation_1m', 0.0)
        if separation > 1.0:
            score += min(10.0, separation * 2.0)  # Up to 10 bonus points
    
    # Add slope bonus for 1m
    slope_1m = features.get('ema9_slope_1m', 0.0)
    if slope_1m > 0:
        score += min(10.0, slope_1m * 0.5)  # Up to 10 bonus points
    
    # 5m momentum (30% weight) - confirms structure
    if features.get('ema_aligned_5m', False):
        score += 30.0
        # Bonus for separation
        separation = features.get('ema_separation_5m', 0.0)
        if separation > 1.0:
            score += min(10.0, separation * 2.0)  # Up to 10 bonus points
    
    # Add slope bonus for 5m
    slope_5m = features.get('ema9_slope_5m', 0.0)
    if slope_5m > 0:
        score += min(10.0, slope_5m * 0.5)  # Up to 10 bonus points
    
    return min(100.0, score)


def score_volatility(features: Dict[str, Any]) -> float:
    """
    Score volatility based on ATR level and expansion (5m)
    Returns 0-100 score
    """
    score = 0.0
    
    atr_5m = features.get('atr_5m', 0.0)
    current_price = features.get('current_price', 1.0)
    
    if current_price > 0 and atr_5m > 0:
        # ATR as percentage of price
        atr_pct = (atr_5m / current_price) * 100
        
        # Score based on ATR level
        if atr_pct >= 3.0:
            score = 100.0  # Very high volatility
        elif atr_pct >= 2.0:
            score = 75.0  # High volatility
        elif atr_pct >= 1.5:
            score = 50.0  # Moderate volatility
        elif atr_pct >= 1.0:
            score = 25.0  # Low volatility
        else:
            score = 0.0  # Very low volatility
        
        # Bonus for ATR expansion
        atr_expansion = features.get('atr_expansion_5m', 0.0)
        if atr_expansion > 10:  # ATR expanding by >10%
            score = min(100.0, score + 15.0)  # Bonus up to 15 points
    
    return score


def score_liquidity(features: Dict[str, Any]) -> float:
    """
    Score liquidity based on relative volume (1m + 5m)
    Returns 0-100 score
    """
    score = 0.0
    
    rel_vol_1m = features.get('rel_volume_1m', 1.0)
    rel_vol_5m = features.get('rel_volume_5m', 1.0)
    
    # Average relative volume
    avg_rel_vol = (rel_vol_1m + rel_vol_5m) / 2.0
    
    # Score based on relative volume
    if avg_rel_vol >= 2.0:
        score = 100.0  # Very high activity
    elif avg_rel_vol >= 1.5:
        score = 75.0  # High activity
    elif avg_rel_vol >= 1.2:
        score = 50.0  # Moderate activity
    elif avg_rel_vol >= 1.0:
        score = 25.0  # Normal activity
    else:
        score = 0.0  # Low activity
    
    return score


def score_stability(features: Dict[str, Any]) -> float:
    """
    Score stability by penalizing high divergence between 1m and 5m
    Returns 0-100 score (higher = more stable)
    """
    divergence = features.get('stability_divergence', 0.0)
    
    # Lower divergence = higher stability score
    if divergence < 0.5:
        score = 100.0  # Very stable
    elif divergence < 1.0:
        score = 75.0  # Stable
    elif divergence < 2.0:
        score = 50.0  # Moderate stability
    elif divergence < 5.0:
        score = 25.0  # Low stability
    else:
        score = 0.0  # Very noisy
    
    return score


def detect_direction(features: Dict[str, Any]) -> Tuple[Direction, float, str]:
    """
    Detect trade direction based on momentum and price action.
    
    Returns:
        (direction, confidence, reason)
        - direction: "LONG", "SHORT", or "NEUTRAL"
        - confidence: 0-100 how confident in direction
        - reason: explanation
    """
    bullish_signals = 0
    bearish_signals = 0
    reasons = []
    
    # 1. EMA Alignment (strongest signal)
    # Bullish: price > EMA9 > EMA21 (aligned upward)
    # Bearish: price < EMA9 < EMA21 (aligned downward)
    ema_aligned_1m = features.get('ema_aligned_1m', False)
    ema_aligned_5m = features.get('ema_aligned_5m', False)
    
    # Check slope direction
    slope_1m = features.get('ema9_slope_1m', 0.0)
    slope_5m = features.get('ema9_slope_5m', 0.0)
    
    if slope_1m > 0 and slope_5m > 0:
        bullish_signals += 2
        reasons.append("EMAs sloping up")
    elif slope_1m < 0 and slope_5m < 0:
        bearish_signals += 2
        reasons.append("EMAs sloping down")
    
    if ema_aligned_1m and ema_aligned_5m:
        if slope_1m > 0:
            bullish_signals += 2
            reasons.append("EMA alignment bullish")
        elif slope_1m < 0:
            bearish_signals += 2
            reasons.append("EMA alignment bearish")
    
    # 2. Price vs VWAP (if available)
    current_price = features.get('current_price', 0)
    vwap = features.get('vwap', 0)
    if current_price > 0 and vwap > 0:
        if current_price > vwap * 1.002:  # >0.2% above VWAP
            bullish_signals += 1
            reasons.append("Above VWAP")
        elif current_price < vwap * 0.998:  # >0.2% below VWAP
            bearish_signals += 1
            reasons.append("Below VWAP")
    
    # 3. Recent price action (close vs open of recent bars)
    recent_return = features.get('recent_return_5m', 0)
    if recent_return > 0.3:  # >0.3% up
        bullish_signals += 1
        reasons.append("Recent price up")
    elif recent_return < -0.3:  # >0.3% down
        bearish_signals += 1
        reasons.append("Recent price down")
    
    # 4. Volume confirmation
    rel_vol = features.get('rel_volume_1m', 1.0)
    if rel_vol > 1.5:
        # High volume confirms the direction
        if bullish_signals > bearish_signals:
            bullish_signals += 1
            reasons.append("Volume confirms up")
        elif bearish_signals > bullish_signals:
            bearish_signals += 1
            reasons.append("Volume confirms down")
    
    # Calculate direction and confidence
    total_signals = bullish_signals + bearish_signals
    
    if total_signals == 0:
        return "NEUTRAL", 0, "No clear signals"
    
    if bullish_signals > bearish_signals:
        confidence = (bullish_signals / (total_signals + 2)) * 100  # +2 to moderate confidence
        return "LONG", min(95, confidence), " | ".join(reasons)
    elif bearish_signals > bullish_signals:
        confidence = (bearish_signals / (total_signals + 2)) * 100
        return "SHORT", min(95, confidence), " | ".join(reasons)
    else:
        return "NEUTRAL", 30, "Mixed signals"


def apply_market_state_adjustment(base_score: float, market_state: Literal["GREEN", "YELLOW", "RED"]) -> Tuple[float, str]:
    """
    Apply MarketState adjustment using PENALTIES (not bonuses)
    
    Returns:
        (adjusted_score, adjustment_reason)
    """
    if market_state == "RED":
        # Should be vetoed before this, but handle gracefully
        return 0.0, "RED state veto"
    elif market_state == "YELLOW":
        # Apply penalty: cap score or reduce by 10
        adjusted = max(0.0, base_score - 10.0)
        return adjusted, "YELLOW state penalty (-10)"
    else:  # GREEN
        # No penalty
        return base_score, "GREEN state (no penalty)"


def calculate_opportunity_score(
    features: Dict[str, Any],
    market_state: Literal["GREEN", "YELLOW", "RED"]
) -> Dict[str, Any]:
    """
    Calculate total opportunity score (0-100) and component scores
    
    Args:
        features: Feature dict from extract_features()
        market_state: "GREEN", "YELLOW", or "RED"
    
    Returns:
        Dict with:
        - opportunity_score: 0-100 total score (after MarketState adjustment)
        - momentum_score: 0-100 momentum component
        - volatility_score: 0-100 volatility component
        - liquidity_score: 0-100 liquidity component
        - stability_score: 0-100 stability component
        - market_state_adjustment: Adjustment reason
        - why: List of explanation strings
    """
    # Calculate component scores
    momentum = score_momentum(features)
    volatility = score_volatility(features)
    liquidity = score_liquidity(features)
    stability = score_stability(features)
    
    # Weighted average (before MarketState adjustment)
    # Momentum: 40%, Volatility: 25%, Liquidity: 20%, Stability: 15%
    base_score = (
        momentum * 0.40 +
        volatility * 0.25 +
        liquidity * 0.20 +
        stability * 0.15
    )
    
    # Apply MarketState adjustment (penalties, not bonuses)
    adjusted_score, adjustment_reason = apply_market_state_adjustment(base_score, market_state)
    
    # Build explanation
    why = []
    if momentum > 0:
        why.append(f"Momentum: {momentum:.1f} (EMA alignment)")
    if volatility > 0:
        why.append(f"Volatility: {volatility:.1f} (ATR expansion)")
    if liquidity > 0:
        why.append(f"Liquidity: {liquidity:.1f} (relative volume)")
    if stability > 0:
        why.append(f"Stability: {stability:.1f} (low divergence)")
    if adjustment_reason:
        why.append(f"MarketState: {adjustment_reason}")
    
    # Detect direction
    direction, direction_confidence, direction_reason = detect_direction(features)
    why.append(f"Direction: {direction} ({direction_confidence:.0f}% - {direction_reason})")
    
    return {
        "opportunity_score": round(adjusted_score, 2),
        "momentum_score": round(momentum, 2),
        "volatility_score": round(volatility, 2),
        "liquidity_score": round(liquidity, 2),
        "stability_score": round(stability, 2),
        "market_state_adjustment": adjustment_reason,
        "direction": direction,
        "direction_confidence": round(direction_confidence, 1),
        "direction_reason": direction_reason,
        "why": why
    }
