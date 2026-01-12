"""
ZERO Scanner - Horizon Definitions
Defines time horizons for candidate discovery
"""

from typing import Literal
from datetime import timedelta

# Horizon types
HorizonType = Literal["H30", "H2H", "HDAY", "HWEEK"]

# Horizon definitions
HORIZON_DEFINITIONS = {
    "H30": {
        "name": "30 Minutes",
        "duration_seconds": 30 * 60,  # 1800 seconds
        "lookback_minutes": 60,  # Look back 60 minutes for context
        "candidate_type": "INTRADAY"
    },
    "H2H": {
        "name": "2 Hours",
        "duration_seconds": 2 * 60 * 60,  # 7200 seconds
        "lookback_minutes": 240,  # Look back 4 hours for context
        "candidate_type": "INTRADAY"
    },
    "HDAY": {
        "name": "Daily",
        "duration_seconds": 24 * 60 * 60,  # 86400 seconds
        "lookback_minutes": 1440,  # Look back 1 day for context
        "candidate_type": "SWING"
    },
    "HWEEK": {
        "name": "Weekly",
        "duration_seconds": 7 * 24 * 60 * 60,  # 604800 seconds
        "lookback_minutes": 10080,  # Look back 1 week for context
        "candidate_type": "SWING"
    }
}


def get_horizon_info(horizon: HorizonType) -> dict:
    """Get horizon information"""
    return HORIZON_DEFINITIONS.get(horizon, {})


def get_intraday_horizons() -> list[HorizonType]:
    """Get list of intraday horizons"""
    return ["H30", "H2H"]


def get_swing_horizons() -> list[HorizonType]:
    """Get list of swing horizons"""
    return ["HDAY", "HWEEK"]


def get_all_horizons() -> list[HorizonType]:
    """Get all horizons"""
    return ["H30", "H2H", "HDAY", "HWEEK"]

