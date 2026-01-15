"""
Morning Brief Generator - SPEC_LOCK §4.1

Produces Morning Brief daily without manual intervention.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class MorningBriefGenerator:
    """
    Generates daily Morning Brief automatically.
    
    Output:
    - MarketState summary
    - AttentionState summary  
    - Stand-down warnings
    - Expected volatility regime
    - Top 3 watch sectors/themes
    - Model confidence status
    """
    
    def __init__(self, core_engine):
        self.core = core_engine
    
    async def generate(self) -> Dict[str, Any]:
        """Generate the morning brief"""
        timestamp = datetime.now(timezone.utc)
        
        # Get current states
        market_state = await self._get_market_state()
        attention_state = await self._get_attention_state()
        calibration_state = await self._get_calibration_state()
        
        # Build brief
        brief = {
            "schema_version": "1.0",
            "timestamp": timestamp.isoformat(),
            "date": timestamp.strftime("%Y-%m-%d"),
            "day_type": self._determine_day_type(market_state, attention_state),
            
            # Market State Summary
            "market_summary": {
                "state": market_state.get("state", "UNKNOWN"),
                "vixy_price": market_state.get("vixy_price"),
                "reason": market_state.get("reason", ""),
                "trading_allowed": market_state.get("state") in ["GREEN", "YELLOW"],
                "caution_level": self._get_caution_level(market_state)
            },
            
            # Attention Summary
            "attention_summary": {
                "score": attention_state.get("attention_stability_score", 50),
                "bucket": attention_state.get("attention_bucket", "UNSTABLE"),
                "risk_state": attention_state.get("risk_on_off_state", "NEUTRAL"),
                "correlation": attention_state.get("correlation_regime", "Unknown"),
                "dominant_sectors": attention_state.get("dominant_sectors", [])
            },
            
            # Stand-down Warnings
            "stand_down_warnings": self._get_stand_down_warnings(market_state, attention_state, calibration_state),
            
            # Volatility Regime
            "volatility_regime": self._get_volatility_regime(market_state),
            
            # Viable Horizons
            "viable_horizons": self._get_viable_horizons(attention_state),
            
            # Model Confidence
            "model_confidence": self._get_model_confidence(calibration_state),
            
            # Action Guidance
            "action_guidance": self._get_action_guidance(market_state, attention_state, calibration_state),
            
            # Human-readable summary
            "narrative": self._generate_narrative(market_state, attention_state, calibration_state)
        }
        
        return brief
    
    async def _get_market_state(self) -> Dict[str, Any]:
        try:
            import json
            data = await self.core.redis_client.get("key:market_state")
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Error getting market state: {e}")
        return {"state": "UNKNOWN"}
    
    async def _get_attention_state(self) -> Dict[str, Any]:
        try:
            import json
            data = await self.core.redis_client.get("key:attention_state")
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Error getting attention state: {e}")
        return {"attention_stability_score": 50, "attention_bucket": "UNSTABLE"}
    
    async def _get_calibration_state(self) -> Dict[str, Any]:
        try:
            import json
            data = await self.core.redis_client.get("key:calibration_state")
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Error getting calibration state: {e}")
        return {"global_stats": {"global_shrink": 1.0}}
    
    def _determine_day_type(self, market: Dict, attention: Dict) -> str:
        """Determine the type of trading day"""
        state = market.get("state", "UNKNOWN")
        bucket = attention.get("attention_bucket", "UNSTABLE")
        
        if state == "RED":
            return "NO_TRADE"
        elif state == "YELLOW" or bucket == "CHAOTIC":
            return "CAUTION"
        elif bucket == "UNSTABLE":
            return "SELECTIVE"
        elif bucket == "STABLE" and state == "GREEN":
            return "NORMAL"
        return "UNCERTAIN"
    
    def _get_caution_level(self, market: Dict) -> str:
        """Get caution level from market state"""
        state = market.get("state", "UNKNOWN")
        if state == "RED":
            return "EXTREME"
        elif state == "YELLOW":
            return "ELEVATED"
        return "NORMAL"
    
    def _get_stand_down_warnings(self, market: Dict, attention: Dict, calibration: Dict) -> List[str]:
        """Get list of stand-down warnings"""
        warnings = []
        
        if market.get("state") == "RED":
            warnings.append(f"🔴 MARKET HALTED: {market.get('reason', 'Unknown reason')}")
        
        if market.get("state") == "YELLOW":
            warnings.append(f"🟡 ELEVATED CAUTION: {market.get('reason', 'Unknown reason')}")
        
        if attention.get("attention_bucket") == "CHAOTIC":
            warnings.append("⚠️ CHAOTIC ATTENTION: Only H30 horizons allowed")
        
        shrink = calibration.get("global_stats", {}).get("global_shrink", 1.0)
        if shrink < 0.7:
            warnings.append(f"📉 MODEL DEGRADED: Confidence reduced to {shrink*100:.0f}%")
        
        degraded_horizons = calibration.get("degraded_horizons", [])
        if degraded_horizons:
            warnings.append(f"⏰ DEGRADED HORIZONS: {', '.join(degraded_horizons)}")
        
        return warnings
    
    def _get_volatility_regime(self, market: Dict) -> Dict[str, Any]:
        """Get volatility regime info"""
        vixy = market.get("vixy_price")
        
        if vixy is None:
            regime = "UNKNOWN"
            description = "Volatility data unavailable"
        elif vixy >= 25:
            regime = "EXTREME"
            description = "Extreme volatility - trading halted"
        elif vixy >= 20:
            regime = "ELEVATED"
            description = "Elevated volatility - reduced position sizes"
        elif vixy >= 15:
            regime = "NORMAL"
            description = "Normal volatility conditions"
        else:
            regime = "LOW"
            description = "Low volatility - watch for breakouts"
        
        return {
            "regime": regime,
            "vixy_price": vixy,
            "description": description
        }
    
    def _get_viable_horizons(self, attention: Dict) -> List[str]:
        """Get list of viable horizons based on attention"""
        bucket = attention.get("attention_bucket", "UNSTABLE")
        
        if bucket == "CHAOTIC":
            return ["H30"]
        elif bucket == "UNSTABLE":
            return ["H30", "H2H", "HDAY"]
        else:
            return ["H30", "H2H", "HDAY", "HWEEK"]
    
    def _get_model_confidence(self, calibration: Dict) -> Dict[str, Any]:
        """Get model confidence status"""
        global_stats = calibration.get("global_stats", {})
        shrink = global_stats.get("global_shrink", 1.0)
        total_evals = global_stats.get("total_evaluations", 0)
        
        if shrink >= 0.9:
            status = "NORMAL"
            description = "Model performing within expectations"
        elif shrink >= 0.7:
            status = "REDUCED"
            description = "Model accuracy below target - probabilities reduced"
        else:
            status = "DEGRADED"
            description = "Model significantly underperforming - exercise caution"
        
        return {
            "status": status,
            "shrink_factor": shrink,
            "confidence_pct": round(shrink * 100, 1),
            "total_evaluations": total_evals,
            "description": description
        }
    
    def _get_action_guidance(self, market: Dict, attention: Dict, calibration: Dict) -> Dict[str, Any]:
        """Get action guidance for the day"""
        state = market.get("state", "UNKNOWN")
        bucket = attention.get("attention_bucket", "UNSTABLE")
        shrink = calibration.get("global_stats", {}).get("global_shrink", 1.0)
        
        if state == "RED":
            return {
                "primary_action": "DO NOT TRADE",
                "reason": "Market state is RED - all trading halted",
                "position_sizing": "0%",
                "focus": "Wait for conditions to improve"
            }
        
        if bucket == "CHAOTIC":
            return {
                "primary_action": "SCALPS ONLY",
                "reason": "Chaotic attention - only shortest horizons viable",
                "position_sizing": "25-50%",
                "focus": "H30 setups with tight stops"
            }
        
        if state == "YELLOW" or shrink < 0.7:
            return {
                "primary_action": "SELECTIVE",
                "reason": "Elevated caution or degraded model",
                "position_sizing": "50-75%",
                "focus": "High-conviction setups only"
            }
        
        if bucket == "UNSTABLE":
            return {
                "primary_action": "NORMAL WITH CAUTION",
                "reason": "Unstable attention - longer horizons gated",
                "position_sizing": "75-100%",
                "focus": "H30, H2H, HDAY setups"
            }
        
        return {
            "primary_action": "NORMAL",
            "reason": "Favorable conditions",
            "position_sizing": "100%",
            "focus": "All horizons viable"
        }
    
    def _generate_narrative(self, market: Dict, attention: Dict, calibration: Dict) -> str:
        """Generate human-readable narrative"""
        state = market.get("state", "UNKNOWN")
        bucket = attention.get("attention_bucket", "UNSTABLE")
        score = attention.get("attention_stability_score", 50)
        risk = attention.get("risk_on_off_state", "NEUTRAL")
        shrink = calibration.get("global_stats", {}).get("global_shrink", 1.0)
        vixy = market.get("vixy_price")
        
        parts = []
        
        # Opening
        if state == "RED":
            parts.append("🔴 Today is a NO-TRADE day.")
        elif state == "YELLOW":
            parts.append("🟡 Today requires elevated caution.")
        elif bucket == "STABLE":
            parts.append("🟢 Conditions are favorable for trading.")
        else:
            parts.append("🟠 Today is a selective trading day.")
        
        # Volatility
        if vixy:
            parts.append(f"VIXY is at ${vixy:.2f}.")
        
        # Attention
        parts.append(f"Market attention is {bucket} (score: {score:.0f}).")
        
        # Risk
        if risk == "RISK_ON":
            parts.append("Risk appetite is elevated.")
        elif risk == "RISK_OFF":
            parts.append("Risk appetite is defensive.")
        
        # Model confidence
        if shrink < 0.9:
            parts.append(f"Model confidence is reduced to {shrink*100:.0f}%.")
        
        # Horizons
        if bucket == "CHAOTIC":
            parts.append("Only H30 (30-min) horizons are viable.")
        elif bucket == "UNSTABLE":
            parts.append("HWEEK horizons are gated.")
        
        return " ".join(parts)
