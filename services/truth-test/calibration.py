"""
ZERO Truth Test - Calibration Engine

Computes shrink factors based on historical pass rates.
Per SPEC_LOCK §6.2: Only shrink probabilities, never boost above raw.

CONFIDENCE DEGRADATION RULES (MANDATORY):
- Deviation 5-10%:  Shrink by 10% (multiplier = 0.90)
- Deviation 10-20%: Shrink by 25% (multiplier = 0.75)
- Deviation >20%:   Force YELLOW regime bias (multiplier = 0.50)

These adjustments:
- Apply per bucket (horizon × market_state × attention_bucket)
- Are multiplicative, not absolute
- Are reversible if calibration recovers
- NEVER increase probabilities beyond original
"""

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def compute_shrink_factor(
    observed_win_rate: float, 
    expected_probability: float,
    sample_size: int
) -> float:
    """
    Compute shrink factor based on deviation between observed and expected.
    
    Per SPEC_LOCK Confidence Degradation Rules:
    - Deviation 5-10%:  Shrink by 10% (multiplier = 0.90)
    - Deviation 10-20%: Shrink by 25% (multiplier = 0.75)
    - Deviation >20%:   Force conservative (multiplier = 0.50)
    
    Args:
        observed_win_rate: Actual pass rate (PASS / (PASS + FAIL))
        expected_probability: Average probability issued for this bucket
        sample_size: Number of signals in bucket
    
    Returns:
        Shrink factor (0.0 to 1.0) - NEVER > 1.0
    """
    # Require minimum sample size for meaningful calibration
    MIN_SAMPLE_SIZE = 10
    
    if sample_size < MIN_SAMPLE_SIZE:
        # Not enough data - use conservative default
        logger.info(f"Insufficient samples ({sample_size} < {MIN_SAMPLE_SIZE}), using default shrink=0.90")
        return 0.90
    
    # Calculate deviation: how much worse than expected?
    # Positive deviation = we're overconfident (observed < expected)
    if expected_probability > 0:
        deviation = expected_probability - observed_win_rate
    else:
        deviation = 0.0
    
    # Apply degradation rules based on deviation
    if deviation > 0.20:
        # >20% deviation - Force YELLOW regime bias (heavy shrink)
        shrink = 0.50
        logger.warning(f"HEAVY SHRINK: deviation={deviation:.1%} > 20%, shrink=0.50")
    elif deviation > 0.10:
        # 10-20% deviation - Shrink by 25%
        shrink = 0.75
        logger.info(f"MODERATE SHRINK: deviation={deviation:.1%} (10-20%), shrink=0.75")
    elif deviation > 0.05:
        # 5-10% deviation - Shrink by 10%
        shrink = 0.90
        logger.info(f"LIGHT SHRINK: deviation={deviation:.1%} (5-10%), shrink=0.90")
    elif deviation > 0:
        # 0-5% deviation - Minimal shrink
        shrink = 0.95
    else:
        # Observed >= expected - no shrink needed (but NEVER boost)
        shrink = 1.00
    
    return shrink


def compute_brier_score(predictions: List[float], outcomes: List[int]) -> float:
    """
    Compute Brier score for calibration assessment.
    Lower is better (0 = perfect, 1 = worst).
    
    Brier = mean((prediction - outcome)^2)
    """
    if not predictions or len(predictions) != len(outcomes):
        return 1.0
    
    n = len(predictions)
    brier = sum((p - o) ** 2 for p, o in zip(predictions, outcomes)) / n
    return brier


def aggregate_calibration(
    performance_data: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Aggregate calibration metrics and compute shrink factors.
    
    Args:
        performance_data: Results from db.get_calibration_data()
    
    Returns:
        Calibration state dict for Redis key:calibration_state
    """
    calibration = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0",
        "buckets": {},
        "confidence_multipliers": {},  # Per-bucket multipliers for easy lookup
        "degraded_horizons": [],
        "degraded_states": [],
        "global_stats": {
            "total_signals": 0,
            "total_pass": 0,
            "total_fail": 0,
            "global_pass_rate": 0.0,
            "global_avg_probability": 0.0,
            "global_shrink": 1.0
        }
    }
    
    total_signals = 0
    total_pass = 0
    total_fail = 0
    total_prob_sum = 0.0
    degraded_horizons = set()
    degraded_states = set()
    
    for row in performance_data:
        horizon = row["horizon"]
        regime = row["regime_state"]
        attention = row.get("attention_bucket") or "UNKNOWN"
        
        # Create bucket key
        bucket_key = f"{horizon}_{regime}_{attention}"
        
        pass_count = int(row["pass_count"] or 0)
        fail_count = int(row["fail_count"] or 0)
        total = pass_count + fail_count
        
        if total == 0:
            continue
        
        win_rate = pass_count / total
        avg_probability = float(row.get("avg_probability") or 0.5)
        avg_mfe = float(row.get("avg_mfe") or 0)
        avg_mae = float(row.get("avg_mae") or 0)
        
        # Compute shrink factor based on deviation
        shrink_factor = compute_shrink_factor(win_rate, avg_probability, total)
        
        # Track degraded buckets
        if shrink_factor < 1.0:
            degraded_horizons.add(horizon)
            degraded_states.add(regime)
        
        calibration["buckets"][bucket_key] = {
            "horizon": horizon,
            "regime_state": regime,
            "attention_bucket": attention,
            "total_signals": total,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "expired_count": int(row.get("expired_count") or 0),
            "win_rate": round(win_rate, 4),
            "avg_probability": round(avg_probability, 4),
            "avg_mfe": round(avg_mfe, 4),
            "avg_mae": round(avg_mae, 4),
            "shrink_factor": shrink_factor,
            "deviation": round(avg_probability - win_rate, 4)
        }
        
        # Store multiplier for easy lookup
        calibration["confidence_multipliers"][bucket_key] = shrink_factor
        
        total_signals += total
        total_pass += pass_count
        total_fail += fail_count
        total_prob_sum += avg_probability * total
        
        logger.info(
            f"Bucket {bucket_key}: win_rate={win_rate:.2%} vs expected={avg_probability:.2%}, "
            f"shrink={shrink_factor:.2f}, avg_mfe={avg_mfe:.2f}, avg_mae={avg_mae:.2f}"
        )
    
    # Global stats
    if total_signals > 0:
        global_win_rate = total_pass / total_signals
        global_avg_prob = total_prob_sum / total_signals
        calibration["global_stats"]["total_signals"] = total_signals
        calibration["global_stats"]["total_pass"] = total_pass
        calibration["global_stats"]["total_fail"] = total_fail
        calibration["global_stats"]["global_pass_rate"] = round(global_win_rate, 4)
        calibration["global_stats"]["global_avg_probability"] = round(global_avg_prob, 4)
        calibration["global_stats"]["global_shrink"] = compute_shrink_factor(
            global_win_rate, global_avg_prob, total_signals
        )
    
    calibration["degraded_horizons"] = list(degraded_horizons)
    calibration["degraded_states"] = list(degraded_states)
    
    # Build probability_calibration in spec format:
    # { "H30": { "GREEN": { "STABLE": { "predicted": 0.70, "realized": 0.58, "confidence_adjustment": -0.12 } } } }
    probability_calibration = {}
    for bucket_key, bucket_data in calibration["buckets"].items():
        horizon = bucket_data["horizon"]
        regime = bucket_data["regime_state"]
        attention = bucket_data["attention_bucket"]
        
        if horizon not in probability_calibration:
            probability_calibration[horizon] = {}
        if regime not in probability_calibration[horizon]:
            probability_calibration[horizon][regime] = {}
        
        predicted = bucket_data.get("avg_probability", 0.5)
        realized = bucket_data.get("win_rate", 0.0)
        adjustment = realized - predicted  # Negative if overconfident
        
        probability_calibration[horizon][regime][attention] = {
            "predicted": round(predicted, 4),
            "realized": round(realized, 4),
            "confidence_adjustment": round(adjustment, 4),
            "shrink_factor": bucket_data.get("shrink_factor", 1.0),
            "sample_size": bucket_data.get("total_signals", 0)
        }
    
    calibration["probability_calibration"] = probability_calibration
    
    logger.info(
        f"Calibration complete: {len(calibration['buckets'])} buckets, "
        f"{total_signals} total signals, "
        f"win_rate={calibration['global_stats']['global_pass_rate']:.2%}, "
        f"degraded_horizons={calibration['degraded_horizons']}, "
        f"degraded_states={calibration['degraded_states']}"
    )
    
    return calibration


def get_shrink_factor(
    calibration_state: Optional[Dict[str, Any]],
    horizon: str,
    regime_state: str,
    attention_bucket: str
) -> float:
    """
    Get shrink factor for a specific bucket from calibration state.
    Falls back to global shrink if bucket not found.
    
    Args:
        calibration_state: Loaded from Redis key:calibration_state
        horizon: H30, H2H, HDAY, HWEEK
        regime_state: GREEN, YELLOW, RED
        attention_bucket: STABLE, UNSTABLE, CHAOTIC
    
    Returns:
        Shrink factor (0.0 to 1.0)
    """
    if not calibration_state:
        # No calibration data - use conservative default
        return 0.90
    
    bucket_key = f"{horizon}_{regime_state}_{attention_bucket}"
    
    buckets = calibration_state.get("buckets", {})
    if bucket_key in buckets:
        return buckets[bucket_key].get("shrink_factor", 1.0)
    
    # Fall back to global shrink
    global_stats = calibration_state.get("global_stats", {})
    return global_stats.get("global_shrink", 0.90)


def apply_shrink(
    probability_raw: float,
    shrink_factor: float
) -> float:
    """
    Apply shrink factor to probability.
    Per SPEC_LOCK: Never increase above raw, only shrink.
    
    Args:
        probability_raw: Raw probability (0.0 to 1.0)
        shrink_factor: Shrink factor (0.0 to 1.0)
    
    Returns:
        Adjusted probability (clamped to 0.0-1.0)
    """
    # Ensure shrink_factor doesn't boost
    shrink_factor = min(shrink_factor, 1.0)
    
    adjusted = probability_raw * shrink_factor
    
    # Clamp to valid range
    return max(0.0, min(1.0, adjusted))
