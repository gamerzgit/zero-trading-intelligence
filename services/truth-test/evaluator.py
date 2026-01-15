"""
ZERO Truth Test - MFE/MAE Evaluator

Evaluates opportunity outcomes by walking forward through candles
and tracking Maximum Favorable Excursion (MFE) and Maximum Adverse Excursion (MAE).

ASSUMPTION: LONG-only evaluation (documented per SPEC_LOCK)
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Horizon definitions (in minutes)
HORIZON_MINUTES = {
    "H30": 30,
    "H2H": 120,  # 2 hours
    "HDAY": 390,  # Full trading day (6.5 hours)
    "HWEEK": 1950,  # 5 trading days
}


def get_horizon_minutes(horizon: str) -> int:
    """Get horizon duration in minutes"""
    return HORIZON_MINUTES.get(horizon, 120)


def evaluate_opportunity(
    opportunity: Dict[str, Any],
    entry_candle: Optional[Dict[str, Any]],
    forward_candles: List[Dict[str, Any]],
    atr_value: Optional[float],
    evaluation_time: datetime
) -> Dict[str, Any]:
    """
    Evaluate a single opportunity using MFE/MAE analysis.
    
    LONG-only assumption: 
    - MFE = max(high - entry_price) = favorable move UP
    - MAE = max(entry_price - low) = adverse move DOWN
    - PASS = target hit before stop
    - FAIL = stop hit before target
    
    Args:
        opportunity: Opportunity record from opportunity_log
        entry_candle: 1m candle at/after issue time (None if no data)
        forward_candles: Candles from issue time to horizon end
        atr_value: ATR value for converting to absolute prices
        evaluation_time: When this evaluation is being run
    
    Returns:
        Dict with evaluation results for performance_log
    """
    result = {
        "opportunity_id": opportunity["id"],
        "ticker": opportunity["ticker"],
        "horizon": opportunity["horizon"],
        "issued_time": opportunity["time"],
        "regime_state": opportunity["market_state"],
        "attention_stability_score": float(opportunity["attention_stability_score"]),
        "attention_bucket": opportunity.get("attention_bucket"),
        "probability_issued": float(opportunity["probability"]) if opportunity.get("probability") else None,
        "target_atr": float(opportunity["target_atr"]) if opportunity.get("target_atr") else None,
        "stop_atr": float(opportunity["stop_atr"]) if opportunity.get("stop_atr") else None,
        "atr_value": atr_value,
        "evaluation_time": evaluation_time,
        "debug_json": {}
    }
    
    # Case 1: No entry candle found
    if entry_candle is None:
        logger.warning(f"NO_DATA: No entry candle for {opportunity['ticker']} at {opportunity['time']}")
        result["outcome"] = "NO_DATA"
        result["debug_json"]["reason"] = "No entry candle found within 2 minutes of issue time"
        return result
    
    entry_price = float(entry_candle["close"])
    result["entry_price"] = entry_price
    result["debug_json"]["entry_candle_time"] = str(entry_candle["time"])
    
    # Case 2: No ATR value available
    if atr_value is None or atr_value <= 0:
        logger.warning(f"NO_DATA: No ATR value for {opportunity['ticker']}")
        result["outcome"] = "NO_DATA"
        result["debug_json"]["reason"] = "Could not compute ATR value"
        return result
    
    # Case 3: No forward candles
    if not forward_candles:
        logger.warning(f"NO_DATA: No forward candles for {opportunity['ticker']}")
        result["outcome"] = "NO_DATA"
        result["debug_json"]["reason"] = "No candles found for horizon window"
        return result
    
    # Calculate target and stop prices (LONG-only)
    target_atr_mult = float(opportunity["target_atr"]) if opportunity.get("target_atr") else 2.0
    stop_atr_mult = float(opportunity["stop_atr"]) if opportunity.get("stop_atr") else 1.0
    
    target_price = entry_price + (target_atr_mult * atr_value)
    stop_price = entry_price - (stop_atr_mult * atr_value)
    
    result["debug_json"]["target_price"] = target_price
    result["debug_json"]["stop_price"] = stop_price
    result["debug_json"]["candle_count"] = len(forward_candles)
    
    # Walk forward through candles
    mfe = 0.0  # Max Favorable Excursion (positive = good for LONG)
    mae = 0.0  # Max Adverse Excursion (positive = bad for LONG)
    target_hit_time = None
    stop_hit_time = None
    
    for candle in forward_candles:
        high = float(candle["high"])
        low = float(candle["low"])
        candle_time = candle["time"]
        
        # Update MFE (max upward move from entry)
        favorable = high - entry_price
        if favorable > mfe:
            mfe = favorable
        
        # Update MAE (max downward move from entry)
        adverse = entry_price - low
        if adverse > mae:
            mae = adverse
        
        # Check if target hit (LONG: price goes UP to target)
        if target_hit_time is None and high >= target_price:
            target_hit_time = candle_time
        
        # Check if stop hit (LONG: price goes DOWN to stop)
        if stop_hit_time is None and low <= stop_price:
            stop_hit_time = candle_time
    
    # Store realized MFE/MAE
    result["realized_mfe"] = mfe
    result["realized_mae"] = mae
    result["mfe_atr"] = mfe / atr_value if atr_value > 0 else None
    result["mae_atr"] = mae / atr_value if atr_value > 0 else None
    
    # Determine outcome based on which hit first
    # Per spec: SUCCESS if MFE >= target_atr BEFORE MAE >= stop_atr
    resolution_time = None
    
    if target_hit_time is not None and stop_hit_time is not None:
        # Both hit - which was first?
        if target_hit_time <= stop_hit_time:
            result["outcome"] = "PASS"
            result["realized_outcome"] = True  # SUCCESS
            result["target_hit_first"] = True
            result["stop_hit_first"] = False
            result["neither_hit"] = False
            resolution_time = target_hit_time
        else:
            result["outcome"] = "FAIL"
            result["realized_outcome"] = False  # FAILURE
            result["target_hit_first"] = False
            result["stop_hit_first"] = True
            result["neither_hit"] = False
            resolution_time = stop_hit_time
    elif target_hit_time is not None:
        # Only target hit - SUCCESS
        result["outcome"] = "PASS"
        result["realized_outcome"] = True
        result["target_hit_first"] = True
        result["stop_hit_first"] = False
        result["neither_hit"] = False
        resolution_time = target_hit_time
    elif stop_hit_time is not None:
        # Only stop hit - FAILURE
        result["outcome"] = "FAIL"
        result["realized_outcome"] = False
        result["target_hit_first"] = False
        result["stop_hit_first"] = True
        result["neither_hit"] = False
        resolution_time = stop_hit_time
    else:
        # Neither hit - EXPIRED (counts as FAILURE for calibration)
        result["outcome"] = "EXPIRED"
        result["realized_outcome"] = False  # Expired = not a success
        result["target_hit_first"] = False
        result["stop_hit_first"] = False
        result["neither_hit"] = True
        # Resolution time = end of horizon window
        if forward_candles:
            resolution_time = forward_candles[-1]["time"]
    
    # Calculate time_to_resolution (seconds from issue to resolution)
    issue_time = opportunity["time"]
    if resolution_time is not None:
        time_delta = resolution_time - issue_time
        result["time_to_resolution"] = time_delta.total_seconds()
    else:
        result["time_to_resolution"] = None
    
    result["debug_json"]["target_hit_time"] = str(target_hit_time) if target_hit_time else None
    result["debug_json"]["stop_hit_time"] = str(stop_hit_time) if stop_hit_time else None
    result["debug_json"]["resolution_time"] = str(resolution_time) if resolution_time else None
    
    logger.info(
        f"Evaluated {opportunity['ticker']} ({opportunity['horizon']}): "
        f"{result['outcome']} | MFE={mfe:.4f} MAE={mae:.4f} | "
        f"Entry={entry_price:.2f} Target={target_price:.2f} Stop={stop_price:.2f}"
    )
    
    return result
