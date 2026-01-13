"""
ZERO Core Logic - Confidence Calculation
Converts opportunity scores to confidence bands (LOW/MED/HIGH) and confidence_pct
NOTE: This is heuristic until Milestone 6 (Truth Test calibration)
"""

from typing import Literal, Tuple, Dict, Any
import logging

logger = logging.getLogger(__name__)


def score_to_confidence_band(score: float) -> Literal["LOW", "MED", "HIGH"]:
    """
    Convert opportunity score (0-100) to confidence band
    
    Heuristic mapping:
    - Score 0-40: LOW confidence
    - Score 40-70: MED confidence
    - Score 70-100: HIGH confidence
    
    Args:
        score: Opportunity score (0-100)
    
    Returns:
        Confidence band: "LOW", "MED", or "HIGH"
    """
    score = max(0.0, min(100.0, score))
    
    if score < 40.0:
        return "LOW"
    elif score < 70.0:
        return "MED"
    else:
        return "HIGH"


def score_to_confidence_pct(score: float, market_state: str) -> float:
    """
    Convert opportunity score (0-100) to confidence percentage (0.0-0.95)
    
    NOTE: This is a HEURISTIC until Milestone 6 (Truth Test calibration).
    Do NOT claim this is real-world probability.
    
    Uses a sigmoid-like curve:
    - Score 0-50: Linear mapping (0.0-0.50)
    - Score 50-100: Exponential curve (0.50-0.95)
    
    MarketState YELLOW reduces confidence further.
    
    Args:
        score: Opportunity score (0-100)
        market_state: "GREEN", "YELLOW", or "RED"
    
    Returns:
        Confidence percentage (0.0-0.95) - HEURISTIC ONLY
    """
    # Clamp score to 0-100
    score = max(0.0, min(100.0, score))
    
    if score <= 50.0:
        # Linear mapping for lower scores: 0-50 -> 0.0-0.50
        confidence_pct = score / 100.0
    else:
        # Exponential curve for higher scores: 50-100 -> 0.50-0.95
        normalized = (score - 50.0) / 50.0
        confidence_pct = 0.5 + 0.45 * (normalized ** 1.5)  # 1.5 power for smooth curve
    
    # Apply MarketState YELLOW penalty (reduce confidence)
    if market_state == "YELLOW":
        confidence_pct = confidence_pct * 0.85  # Reduce by 15%
    
    # Cap at 0.95 (nothing is certain)
    confidence_pct = min(0.95, confidence_pct)
    
    return round(confidence_pct, 4)


def calculate_target_stop_atr(
    current_price: float,
    atr: float,
    horizon: str
) -> Tuple[float, float]:
    """
    Calculate target and stop levels in ATR multiples based on horizon
    
    Args:
        current_price: Current price
        atr: Average True Range value
        horizon: "H30", "H2H", "HDAY", or "HWEEK"
    
    Returns:
        (target_atr, stop_atr) - ATR multiples for target and stop
    """
    # Different ATR multiples for different horizons
    horizon_multipliers = {
        "H30": (1.5, 0.75),   # 30-min: 1.5 ATR target, 0.75 ATR stop
        "H2H": (2.0, 1.0),    # 2-hour: 2.0 ATR target, 1.0 ATR stop
        "HDAY": (3.0, 1.5),   # Daily: 3.0 ATR target, 1.5 ATR stop
        "HWEEK": (5.0, 2.5),  # Weekly: 5.0 ATR target, 2.5 ATR stop
    }
    
    target_mult, stop_mult = horizon_multipliers.get(horizon, (2.0, 1.0))
    
    return target_mult, stop_mult


def enrich_opportunity(
    score_data: Dict[str, Any],
    ticker: str,
    horizon: str,
    market_state: str,
    current_price: float,
    atr: float,
    attention_stability_score: float = 50.0  # Default if not available
) -> Dict[str, Any]:
    """
    Enrich opportunity with confidence and ATR levels
    
    Args:
        score_data: Output from calculate_opportunity_score()
        ticker: Stock symbol
        horizon: "H30", "H2H", "HDAY", or "HWEEK"
        market_state: "GREEN", "YELLOW", or "RED"
        current_price: Current price
        atr: Average True Range value
        attention_stability_score: Attention stability score (0-100)
    
    Returns:
        Enriched opportunity dict with confidence_pct, confidence_band, target_atr, stop_atr, etc.
    """
    opportunity_score = score_data["opportunity_score"]
    
    # Calculate confidence band and confidence_pct (HEURISTIC)
    confidence_band = score_to_confidence_band(opportunity_score)
    confidence_pct = score_to_confidence_pct(opportunity_score, market_state)
    
    # Calculate target and stop ATR multiples
    target_atr, stop_atr = calculate_target_stop_atr(current_price, atr, horizon)
    
    # Derive attention bucket from stability score
    if attention_stability_score >= 70:
        attention_bucket = "STABLE"
    elif attention_stability_score >= 40:
        attention_bucket = "UNSTABLE"
    else:
        attention_bucket = "CHAOTIC"
    
    # Calculate attention alignment (placeholder - would use actual attention state)
    if market_state == "GREEN" and attention_stability_score >= 70:
        attention_alignment = 80.0
    elif market_state == "GREEN":
        attention_alignment = 60.0
    else:
        attention_alignment = 40.0
    
    return {
        "ticker": ticker,
        "horizon": horizon,
        "opportunity_score": opportunity_score,
        "confidence_pct": confidence_pct,  # HEURISTIC - not real probability
        "confidence_band": confidence_band,
        "target_atr": target_atr,
        "stop_atr": stop_atr,
        "market_state": market_state,
        "attention_stability_score": attention_stability_score,
        "attention_bucket": attention_bucket,
        "attention_alignment": round(attention_alignment, 2),
        "why": score_data.get("why", []),
        "momentum_score": score_data.get("momentum_score", 0.0),
        "volatility_score": score_data.get("volatility_score", 0.0),
        "liquidity_score": score_data.get("liquidity_score", 0.0),
        "stability_score": score_data.get("stability_score", 0.0),
        "market_state_adjustment": score_data.get("market_state_adjustment", ""),
    }
