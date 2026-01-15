"""
ZERO Truth Test - Calibration Engine

Computes shrink factors based on historical pass rates.
Per SPEC_LOCK §6.2: Only shrink probabilities, never boost above raw.
"""

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def compute_shrink_factor(pass_rate: float, sample_size: int) -> float:
    """
    Compute conservative shrink factor based on pass rate.
    
    Per SPEC_LOCK:
    - Never boost above 1.0 (only shrink)
    - More aggressive shrink for poor performance
    - Require minimum sample size for confidence
    
    Args:
        pass_rate: Actual pass rate (PASS / (PASS + FAIL))
        sample_size: Number of signals in bucket
    
    Returns:
        Shrink factor (0.0 to 1.0)
    """
    # Require minimum sample size for meaningful calibration
    MIN_SAMPLE_SIZE = 10
    
    if sample_size < MIN_SAMPLE_SIZE:
        # Not enough data - use conservative default
        logger.info(f"Insufficient samples ({sample_size} < {MIN_SAMPLE_SIZE}), using default shrink=0.90")
        return 0.90
    
    # Shrink factor based on pass rate
    # More aggressive shrink for poor performance
    if pass_rate < 0.35:
        # Very poor performance - heavy shrink
        shrink = 0.50
    elif pass_rate < 0.45:
        # Below expectation - moderate shrink
        shrink = 0.70
    elif pass_rate < 0.50:
        # Slightly below - light shrink
        shrink = 0.85
    elif pass_rate < 0.55:
        # Around expected - minimal shrink
        shrink = 0.95
    else:
        # Good performance - no shrink (but never boost)
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
        "global_stats": {
            "total_signals": 0,
            "total_pass": 0,
            "total_fail": 0,
            "global_pass_rate": 0.0,
            "global_shrink": 1.0
        }
    }
    
    total_signals = 0
    total_pass = 0
    total_fail = 0
    
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
        
        pass_rate = pass_count / total
        shrink_factor = compute_shrink_factor(pass_rate, total)
        
        calibration["buckets"][bucket_key] = {
            "horizon": horizon,
            "regime_state": regime,
            "attention_bucket": attention,
            "total_signals": total,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "expired_count": int(row.get("expired_count") or 0),
            "pass_rate": round(pass_rate, 4),
            "avg_probability": round(float(row.get("avg_probability") or 0), 4),
            "shrink_factor": shrink_factor
        }
        
        total_signals += total
        total_pass += pass_count
        total_fail += fail_count
        
        logger.info(
            f"Bucket {bucket_key}: {pass_count}/{total} = {pass_rate:.2%} pass rate, "
            f"shrink={shrink_factor:.2f}"
        )
    
    # Global stats
    if total_signals > 0:
        global_pass_rate = total_pass / total_signals
        calibration["global_stats"]["total_signals"] = total_signals
        calibration["global_stats"]["total_pass"] = total_pass
        calibration["global_stats"]["total_fail"] = total_fail
        calibration["global_stats"]["global_pass_rate"] = round(global_pass_rate, 4)
        calibration["global_stats"]["global_shrink"] = compute_shrink_factor(
            global_pass_rate, total_signals
        )
    
    logger.info(
        f"Calibration complete: {len(calibration['buckets'])} buckets, "
        f"{total_signals} total signals, "
        f"{calibration['global_stats']['global_pass_rate']:.2%} global pass rate"
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
