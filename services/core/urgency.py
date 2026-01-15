"""
Urgency Layer - SPEC_LOCK Level 4

"Why Now?" - Timing quality separate from setup quality.

NOT entry optimization or micromanaging.
IS cognitive compression for the trader.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Literal
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

UrgencyLevel = Literal["NOW", "SOON", "WATCH", "WAIT", "AVOID"]


class UrgencyEngine:
    """
    Computes urgency/timing signals for opportunities.
    
    Separates:
    - Setup quality (is this a good trade?)
    - Timing quality (is NOW the right time?)
    """
    
    def __init__(self, core_engine):
        self.core = core_engine
    
    async def compute_urgency(
        self,
        ticker: str,
        candles_5m: pd.DataFrame,
        candles_1m: pd.DataFrame,
        opportunity: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compute urgency for an opportunity.
        
        Returns:
            urgency_level: NOW/SOON/WATCH/WAIT/AVOID
            urgency_score: 0-100
            triggers: List of active triggers
            warnings: List of timing warnings
            why_now: Human-readable explanation
        """
        triggers = []
        warnings = []
        urgency_score = 50  # Neutral default
        
        if candles_5m.empty or candles_1m.empty:
            return self._default_urgency("Insufficient data")
        
        # 1. VWAP Analysis
        vwap_signal = self._analyze_vwap(candles_1m)
        if vwap_signal["trigger"]:
            triggers.append(vwap_signal["trigger"])
            urgency_score += vwap_signal["score_delta"]
        if vwap_signal["warning"]:
            warnings.append(vwap_signal["warning"])
            urgency_score += vwap_signal["score_delta"]
        
        # 2. Momentum Analysis
        momentum_signal = self._analyze_momentum(candles_5m, candles_1m)
        if momentum_signal["trigger"]:
            triggers.append(momentum_signal["trigger"])
            urgency_score += momentum_signal["score_delta"]
        if momentum_signal["warning"]:
            warnings.append(momentum_signal["warning"])
            urgency_score += momentum_signal["score_delta"]
        
        # 3. Extension Analysis
        extension_signal = self._analyze_extension(candles_5m)
        if extension_signal["trigger"]:
            triggers.append(extension_signal["trigger"])
            urgency_score += extension_signal["score_delta"]
        if extension_signal["warning"]:
            warnings.append(extension_signal["warning"])
            urgency_score += extension_signal["score_delta"]
        
        # 4. Volume Confirmation
        volume_signal = self._analyze_volume(candles_1m)
        if volume_signal["trigger"]:
            triggers.append(volume_signal["trigger"])
            urgency_score += volume_signal["score_delta"]
        if volume_signal["warning"]:
            warnings.append(volume_signal["warning"])
            urgency_score += volume_signal["score_delta"]
        
        # 5. Breakout Detection
        breakout_signal = self._detect_breakout(candles_5m, candles_1m)
        if breakout_signal["trigger"]:
            triggers.append(breakout_signal["trigger"])
            urgency_score += breakout_signal["score_delta"]
        
        # Clamp score
        urgency_score = max(0, min(100, urgency_score))
        
        # Determine level
        urgency_level = self._score_to_level(urgency_score, triggers, warnings)
        
        # Generate explanation
        why_now = self._generate_why_now(urgency_level, triggers, warnings)
        
        return {
            "urgency_level": urgency_level,
            "urgency_score": round(urgency_score, 1),
            "triggers": triggers,
            "warnings": warnings,
            "why_now": why_now,
            "components": {
                "vwap": vwap_signal,
                "momentum": momentum_signal,
                "extension": extension_signal,
                "volume": volume_signal,
                "breakout": breakout_signal
            }
        }
    
    def _analyze_vwap(self, candles_1m: pd.DataFrame) -> Dict[str, Any]:
        """Analyze VWAP interaction"""
        result = {"trigger": None, "warning": None, "score_delta": 0}
        
        if len(candles_1m) < 20:
            return result
        
        # Compute VWAP
        typical_price = (candles_1m['high'] + candles_1m['low'] + candles_1m['close']) / 3
        cumulative_tp_vol = (typical_price * candles_1m['volume']).cumsum()
        cumulative_vol = candles_1m['volume'].cumsum()
        vwap = cumulative_tp_vol / cumulative_vol
        
        current_price = candles_1m['close'].iloc[-1]
        current_vwap = vwap.iloc[-1]
        prev_price = candles_1m['close'].iloc[-2]
        prev_vwap = vwap.iloc[-2]
        
        # VWAP reclaim (bullish)
        if prev_price < prev_vwap and current_price > current_vwap:
            result["trigger"] = "VWAP_RECLAIM"
            result["score_delta"] = 15
        # VWAP rejection (bearish warning)
        elif prev_price > prev_vwap and current_price < current_vwap:
            result["warning"] = "VWAP_REJECTION"
            result["score_delta"] = -10
        # Trading above VWAP
        elif current_price > current_vwap * 1.002:
            result["trigger"] = "ABOVE_VWAP"
            result["score_delta"] = 5
        # Trading below VWAP
        elif current_price < current_vwap * 0.998:
            result["warning"] = "BELOW_VWAP"
            result["score_delta"] = -5
        
        return result
    
    def _analyze_momentum(self, candles_5m: pd.DataFrame, candles_1m: pd.DataFrame) -> Dict[str, Any]:
        """Analyze momentum strength"""
        result = {"trigger": None, "warning": None, "score_delta": 0}
        
        if len(candles_5m) < 10:
            return result
        
        # Short-term momentum (5 bars)
        short_return = (candles_5m['close'].iloc[-1] / candles_5m['close'].iloc[-5] - 1) * 100
        
        # Very short-term (1m)
        if len(candles_1m) >= 5:
            micro_return = (candles_1m['close'].iloc[-1] / candles_1m['close'].iloc[-5] - 1) * 100
        else:
            micro_return = 0
        
        # Strong momentum
        if short_return > 0.5 and micro_return > 0.1:
            result["trigger"] = "STRONG_MOMENTUM"
            result["score_delta"] = 10
        # Accelerating
        elif micro_return > short_return / 5 and micro_return > 0:
            result["trigger"] = "ACCELERATING"
            result["score_delta"] = 8
        # Fading
        elif short_return > 0 and micro_return < 0:
            result["warning"] = "MOMENTUM_FADING"
            result["score_delta"] = -8
        # Weak
        elif abs(short_return) < 0.1:
            result["warning"] = "WEAK_MOMENTUM"
            result["score_delta"] = -3
        
        return result
    
    def _analyze_extension(self, candles_5m: pd.DataFrame) -> Dict[str, Any]:
        """Analyze price extension from mean"""
        result = {"trigger": None, "warning": None, "score_delta": 0}
        
        if len(candles_5m) < 20:
            return result
        
        # 20-period SMA
        sma20 = candles_5m['close'].rolling(20).mean().iloc[-1]
        current = candles_5m['close'].iloc[-1]
        
        # ATR for context
        tr = candles_5m['high'] - candles_5m['low']
        atr = tr.rolling(14).mean().iloc[-1]
        
        # Extension in ATR terms
        extension = (current - sma20) / atr if atr > 0 else 0
        
        if extension > 2.0:
            result["warning"] = "OVEREXTENDED"
            result["score_delta"] = -15
        elif extension > 1.5:
            result["warning"] = "EXTENDED"
            result["score_delta"] = -8
        elif -0.5 < extension < 0.5:
            result["trigger"] = "NEAR_MEAN"
            result["score_delta"] = 5
        elif extension < -1.5:
            result["trigger"] = "OVERSOLD_BOUNCE"
            result["score_delta"] = 10
        
        return result
    
    def _analyze_volume(self, candles_1m: pd.DataFrame) -> Dict[str, Any]:
        """Analyze volume confirmation"""
        result = {"trigger": None, "warning": None, "score_delta": 0}
        
        if len(candles_1m) < 20:
            return result
        
        avg_volume = candles_1m['volume'].rolling(20).mean().iloc[-1]
        recent_volume = candles_1m['volume'].tail(3).mean()
        
        if avg_volume == 0:
            return result
        
        rvol = recent_volume / avg_volume
        
        if rvol > 2.0:
            result["trigger"] = "VOLUME_SURGE"
            result["score_delta"] = 12
        elif rvol > 1.5:
            result["trigger"] = "ELEVATED_VOLUME"
            result["score_delta"] = 6
        elif rvol < 0.5:
            result["warning"] = "LOW_VOLUME"
            result["score_delta"] = -8
        
        return result
    
    def _detect_breakout(self, candles_5m: pd.DataFrame, candles_1m: pd.DataFrame) -> Dict[str, Any]:
        """Detect breakout conditions"""
        result = {"trigger": None, "warning": None, "score_delta": 0}
        
        if len(candles_5m) < 20:
            return result
        
        # Recent high/low (excluding current bar)
        recent_high = candles_5m['high'].iloc[-20:-1].max()
        recent_low = candles_5m['low'].iloc[-20:-1].min()
        current = candles_5m['close'].iloc[-1]
        
        # Breakout detection
        if current > recent_high:
            result["trigger"] = "BREAKOUT_HIGH"
            result["score_delta"] = 15
        elif current < recent_low:
            result["trigger"] = "BREAKDOWN_LOW"
            result["score_delta"] = -5  # Bearish for longs
        
        # Near breakout level
        elif current > recent_high * 0.995:
            result["trigger"] = "NEAR_BREAKOUT"
            result["score_delta"] = 8
        
        return result
    
    def _score_to_level(self, score: float, triggers: List[str], warnings: List[str]) -> UrgencyLevel:
        """Convert score to urgency level"""
        # Strong triggers override score
        strong_triggers = ["BREAKOUT_HIGH", "VWAP_RECLAIM", "VOLUME_SURGE"]
        if any(t in triggers for t in strong_triggers) and score >= 60:
            return "NOW"
        
        # Strong warnings override score
        strong_warnings = ["OVEREXTENDED", "MOMENTUM_FADING"]
        if any(w in warnings for w in strong_warnings):
            return "WAIT" if score < 40 else "WATCH"
        
        if score >= 75:
            return "NOW"
        elif score >= 60:
            return "SOON"
        elif score >= 45:
            return "WATCH"
        elif score >= 30:
            return "WAIT"
        else:
            return "AVOID"
    
    def _generate_why_now(self, level: UrgencyLevel, triggers: List[str], warnings: List[str]) -> str:
        """Generate human-readable explanation"""
        trigger_explanations = {
            "VWAP_RECLAIM": "Price reclaimed VWAP",
            "ABOVE_VWAP": "Trading above VWAP",
            "STRONG_MOMENTUM": "Strong momentum confirmed",
            "ACCELERATING": "Momentum accelerating",
            "NEAR_MEAN": "Price near mean - good entry zone",
            "OVERSOLD_BOUNCE": "Oversold bounce setup",
            "VOLUME_SURGE": "Volume surge confirms move",
            "ELEVATED_VOLUME": "Elevated volume",
            "BREAKOUT_HIGH": "Breakout above recent high",
            "NEAR_BREAKOUT": "Near breakout level"
        }
        
        warning_explanations = {
            "VWAP_REJECTION": "VWAP rejection - wait for reclaim",
            "BELOW_VWAP": "Below VWAP - caution",
            "MOMENTUM_FADING": "Momentum fading",
            "WEAK_MOMENTUM": "Weak momentum",
            "OVEREXTENDED": "Price overextended - wait for pullback",
            "EXTENDED": "Price extended from mean",
            "LOW_VOLUME": "Low volume - lack of conviction"
        }
        
        parts = []
        
        if level == "NOW":
            parts.append("✅ NOW:")
        elif level == "SOON":
            parts.append("🔜 SOON:")
        elif level == "WATCH":
            parts.append("👀 WATCH:")
        elif level == "WAIT":
            parts.append("⏳ WAIT:")
        else:
            parts.append("🚫 AVOID:")
        
        # Add trigger explanations
        for t in triggers[:2]:
            if t in trigger_explanations:
                parts.append(trigger_explanations[t])
        
        # Add warning explanations
        for w in warnings[:2]:
            if w in warning_explanations:
                parts.append(warning_explanations[w])
        
        if not triggers and not warnings:
            parts.append("No strong signals")
        
        return " | ".join(parts)
    
    def _default_urgency(self, reason: str) -> Dict[str, Any]:
        """Return default urgency when computation fails"""
        return {
            "urgency_level": "WATCH",
            "urgency_score": 50,
            "triggers": [],
            "warnings": [reason],
            "why_now": f"👀 WATCH: {reason}",
            "components": {}
        }
