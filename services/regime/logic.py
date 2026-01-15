"""
ZERO Regime Calculator - Market Permission Logic (Level 0)
"""

import logging
from datetime import datetime, time as dt_time
from typing import Optional, Tuple
import pytz

try:
    import pandas_market_calendars as mcal
    CALENDAR_AVAILABLE = True
except ImportError:
    CALENDAR_AVAILABLE = False
    logging.warning("pandas_market_calendars not available - market hours detection disabled")

logger = logging.getLogger(__name__)

# ET timezone
ET = pytz.timezone('America/New_York')


class RegimeCalculator:
    """
    ZERO Regime Calculator - Determines Market Permission (Level 0)
    
    This is the Veto Layer - can halt everything, never approve alone.
    """
    
    def __init__(self):
        if not CALENDAR_AVAILABLE:
            logger.error("pandas_market_calendars required for market hours detection")
            raise ImportError("Install pandas_market_calendars: pip install pandas-market-calendars")
        
        self.nyse = mcal.get_calendar('NYSE')
        logger.info("✅ Regime Calculator initialized with NYSE calendar")
    
    def get_today_session_bounds(self, now_et: datetime) -> Optional[Tuple[datetime, datetime]]:
        """
        Get today's NYSE session open and close times in ET
        
        Args:
            now_et: Current datetime in ET timezone
            
        Returns:
            Tuple[datetime, datetime] | None: (open_dt_et, close_dt_et) or None if market closed
        """
        try:
            # Get trading schedule for today's date
            schedule = self.nyse.schedule(
                start_date=now_et.date(),
                end_date=now_et.date()
            )
            
            if schedule.empty:
                return None  # Market closed (holiday/weekend)
            
            # Get first (and only) row
            row = schedule.iloc[0]
            open_dt = row['market_open'].to_pydatetime()
            close_dt = row['market_close'].to_pydatetime()
            
            # Ensure timezone-aware
            if open_dt.tzinfo is None:
                open_dt = ET.localize(open_dt)
            if close_dt.tzinfo is None:
                close_dt = ET.localize(close_dt)
            
            return open_dt, close_dt
            
        except Exception as e:
            logger.error(f"Error getting session bounds: {e}")
            return None
    
    def is_open_now(self, now_et: datetime) -> bool:
        """
        Check if market is open right now
        
        Args:
            now_et: Current datetime in ET timezone
            
        Returns:
            bool: True if market is open, False otherwise
        """
        session_bounds = self.get_today_session_bounds(now_et)
        
        if session_bounds is None:
            return False  # Market closed today
        
        open_dt, close_dt = session_bounds
        
        # Check if now is between open and close
        return open_dt <= now_et <= close_dt
    
    def get_time_regime(self, now_et: datetime) -> Tuple[str, str]:
        """
        Get time-of-day regime (only if market is open)
        
        Args:
            now_et: Current datetime in ET timezone
            
        Returns:
            Tuple[str, str]: (time_regime, reason)
            - time_regime: "OPENING", "LUNCH", "PRIME_WINDOW", "CLOSING", "OFF_HOURS"
            - reason: Standardized reason text
        """
        if not self.is_open_now(now_et):
            return "OFF_HOURS", "Off Hours Halt"
        
        session_bounds = self.get_today_session_bounds(now_et)
        if session_bounds is None:
            return "OFF_HOURS", "Off Hours Halt"
        
        open_dt, close_dt = session_bounds
        hour = now_et.hour
        minute = now_et.minute
        time_of_day = now_et.time()
        
        # OPENING: 09:30-10:30 ET
        if hour == 9 and minute >= 30:
            return "OPENING", "Opening Volatility"
        if hour == 10 and minute < 30:
            return "OPENING", "Opening Volatility"
        
        # LUNCH: 11:00-13:00 ET
        if hour >= 11 and hour < 13:
            return "LUNCH", "Lunch Chop"
        
        # PRIME_WINDOW: 13:00-15:00 ET
        if hour >= 13 and hour < 15:
            return "PRIME_WINDOW", "Prime Window"
        
        # CLOSING: 15:00 until session close
        if hour >= 15:
            # Check if we're before session close
            if now_et < close_dt:
                return "CLOSING", "Closing Window"
            else:
                return "OFF_HOURS", "Off Hours Halt"
        
        # Default (shouldn't happen if market is open)
        return "OFF_HOURS", "Off Hours Halt"
    
    def get_volatility_zone(self, vix_level: Optional[float], source_label: str) -> Tuple[str, str]:
        """
        Classify volatility zone based on VIX level from Alpaca API
        
        Args:
            vix_level: VIX level (from Alpaca API - VIX_ALPACA or VIXY_ALPACA)
            source_label: "VIX_ALPACA", "VIXY_ALPACA", or "UNAVAILABLE"
            
        Returns:
            Tuple[str, str]: (zone, reason_suffix)
            - zone: "GREEN", "YELLOW", or "RED"
            - reason_suffix: Text to append to reason
        """
        if vix_level is None:
            return "GREEN", ""  # Default to GREEN if unavailable
        
        # Build reason suffix with source label (from Alpaca)
        # NOTE: VIX is an index, not a stock - we use VIXY ETF as proxy
        # IMPORTANT: vix_level here is actually VIXY price (1:1 approximation)
        # Use VIXY-based thresholds directly (don't convert to VIX)
        if source_label == "VIXY_ALPACA":
            source_text = f"VIXY=${vix_level:.2f} (VIX proxy from Alpaca)"
        else:
            source_text = f"Volatility={vix_level:.2f}"
        
        # VIXY-based thresholds (VIXY price directly, not converted VIX)
        # VIXY typically trades $10-20 in normal conditions, $20-30 in elevated vol, $30+ in panic
        # Adjusted thresholds for VIXY price:
        #   GREEN: VIXY < $20 (normal/low vol)
        #   YELLOW: VIXY $20-25 (elevated vol)
        #   RED: VIXY >= $25 (high vol/panic)
        if vix_level >= 25.0:
            reason = f"Volatility Halt (VIXY >= $25)"
            if source_text:
                reason += f" [{source_text}]"
            return "RED", reason
        elif vix_level >= 20.0:
            reason = f"Elevated Volatility (VIXY $20-25)"
            if source_text:
                reason += f" [{source_text}]"
            return "YELLOW", reason
        else:
            return "GREEN", source_text  # VIXY < $20 is GREEN zone
    
    def calculate_market_state(
        self,
        now_et: datetime,
        vix_level: Optional[float],
        vix_source: str,
        event_risk: bool = False
    ) -> Tuple[str, str]:
        """
        Calculate MarketState (GREEN/YELLOW/RED) with standardized reason
        
        Args:
            now_et: Current datetime in ET timezone
            vix_level: VIX level (or proxy)
            vix_source: "VIX" or "VIXY_PROXY" or "UNAVAILABLE"
            event_risk: Whether major event risk exists
            
        Returns:
            Tuple[str, str]: (state, reason)
            - state: "GREEN", "YELLOW", or "RED"
            - reason: Standardized reason text
        """
        # Check if market is closed (weekend/holiday)
        session_bounds = self.get_today_session_bounds(now_et)
        if session_bounds is None:
            # Check if weekend
            weekday = now_et.weekday()
            if weekday >= 5:  # Saturday (5) or Sunday (6)
                return "RED", "Weekend Halt"
            else:
                return "RED", "Market Holiday Halt"
        
        # Check if off-hours (before open or after close)
        if not self.is_open_now(now_et):
            return "RED", "Off Hours Halt"
        
        # Get time regime
        time_regime, time_reason = self.get_time_regime(now_et)
        
        # Get volatility zone
        vol_zone, vol_reason = self.get_volatility_zone(vix_level, vix_source)
        
        # Combine event risk
        if event_risk:
            return "RED", "Event Risk Halt"
        
        # ============================================================
        # FINAL VETO CALCULATION (Level 0)
        # ============================================================
        
        # 1) RED conditions (Halt)
        if vol_zone == "RED" or vix_level is not None and vix_level >= 25:
            return "RED", vol_reason if vol_reason else "Volatility Halt (>=25)"
        
        # 2) YELLOW conditions (Caution)
        if time_regime in ["OPENING", "LUNCH"]:
            return "YELLOW", time_reason
        if vol_zone == "YELLOW" or (vix_level is not None and vix_level >= 20):
            return "YELLOW", vol_reason if vol_reason else "Elevated Volatility (20-25)"
        
        # 3) GREEN conditions (Full Permission)
        # Prime Window or Closing Window + Low Volatility
        if time_regime in ["PRIME_WINDOW", "CLOSING"]:
            if vix_level is None or vix_level < 20:
                return "GREEN", time_reason
            else:
                # Even in Prime Window, high vol = YELLOW
                return "YELLOW", f"{time_reason} + {vol_reason}" if vol_reason else time_reason
        
        # Default fallback
        return "YELLOW", "Caution"

