"""
Query Mode - SPEC_LOCK §5.2

GET /query?ticker=TSLA

Returns eligibility, reason codes, and full breakdown.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """Result of a ticker query"""
    ticker: str
    timestamp: str
    eligible: bool
    reason_codes: List[str]
    vetoes: List[Dict[str, Any]]
    opportunity: Optional[Dict[str, Any]]
    stand_down: Optional[Dict[str, Any]]
    market_context: Dict[str, Any]
    attention_context: Dict[str, Any]
    calibration_context: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "timestamp": self.timestamp,
            "eligible": self.eligible,
            "reason_codes": self.reason_codes,
            "vetoes": self.vetoes,
            "opportunity": self.opportunity,
            "stand_down": self.stand_down,
            "market_context": self.market_context,
            "attention_context": self.attention_context,
            "calibration_context": self.calibration_context
        }


class QueryEngine:
    """
    Handles on-demand ticker queries.
    
    Unlike scan mode (ZERO talks when it wants), query mode
    lets the trader ask "Why NOT this ticker?"
    """
    
    def __init__(self, core_engine):
        """
        Args:
            core_engine: Reference to the main CoreEngine for accessing
                        market state, attention, calibration, and scoring
        """
        self.core = core_engine
    
    async def query_ticker(self, ticker: str) -> QueryResult:
        """
        Query a specific ticker for eligibility and reasoning.
        
        Returns full breakdown of:
        - Whether ticker is eligible
        - All reason codes (why/why not)
        - Active vetoes
        - Opportunity details if ranked
        - Stand-down explanation if not
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        reason_codes = []
        vetoes = []
        opportunity = None
        stand_down = None
        eligible = True
        
        # 1. Check Market State (Level 0 veto)
        market_state = await self._get_market_state()
        market_context = {
            "state": market_state.get("state", "UNKNOWN"),
            "reason": market_state.get("reason", ""),
            "vixy_price": market_state.get("vixy_price"),
            "market_hours": market_state.get("market_hours", False)
        }
        
        if market_context["state"] == "RED":
            eligible = False
            reason_codes.append("MARKET_STATE_RED")
            vetoes.append({
                "level": 0,
                "type": "MarketState",
                "reason": market_context["reason"],
                "severity": "HARD_VETO"
            })
        elif market_context["state"] == "YELLOW":
            reason_codes.append("MARKET_STATE_YELLOW")
            # YELLOW = penalty, not veto
        
        # 2. Check Attention State (Level 1)
        attention_state = await self._get_attention_state()
        attention_context = {
            "score": attention_state.get("attention_stability_score", 50),
            "bucket": attention_state.get("attention_bucket", "UNSTABLE"),
            "risk_state": attention_state.get("risk_on_off_state", "NEUTRAL"),
            "degraded": attention_state.get("degraded", False)
        }
        
        if attention_context["bucket"] == "CHAOTIC":
            reason_codes.append("ATTENTION_CHAOTIC")
            # Only H30 allowed
        elif attention_context["bucket"] == "UNSTABLE":
            reason_codes.append("ATTENTION_UNSTABLE")
            # HWEEK gated
        
        # 3. Check Calibration State
        calibration_state = await self._get_calibration_state()
        calibration_context = {
            "global_shrink": calibration_state.get("global_stats", {}).get("global_shrink", 1.0),
            "degraded_horizons": calibration_state.get("degraded_horizons", []),
            "degraded_states": calibration_state.get("degraded_states", []),
            "total_evaluations": calibration_state.get("global_stats", {}).get("total_evaluations", 0)
        }
        
        if calibration_context["global_shrink"] < 0.7:
            reason_codes.append("CALIBRATION_DEGRADED")
        
        # 4. Check if ticker has data
        has_data = await self._check_ticker_data(ticker)
        if not has_data:
            eligible = False
            reason_codes.append("NO_DATA")
            vetoes.append({
                "level": 1,
                "type": "Data",
                "reason": f"No recent candle data for {ticker}",
                "severity": "HARD_VETO"
            })
        
        # 5. If still eligible, compute opportunity
        if eligible and has_data:
            try:
                opp = await self._compute_opportunity(ticker, market_context, attention_context, calibration_context)
                if opp:
                    opportunity = opp
                    if opp.get("confidence_pct", 0) < 25:
                        reason_codes.append("LOW_CONFIDENCE")
                    if opp.get("probability", 0) < 0.30:
                        reason_codes.append("LOW_PROBABILITY")
                else:
                    reason_codes.append("SCORING_FAILED")
            except Exception as e:
                logger.error(f"Error computing opportunity for {ticker}: {e}")
                reason_codes.append("SCORING_ERROR")
        
        # 6. Build stand-down explanation if not eligible
        if not eligible or not opportunity:
            stand_down = self._build_stand_down(ticker, reason_codes, vetoes)
        
        # 7. Add positive reason codes if eligible
        if eligible and opportunity:
            if opportunity.get("confidence_pct", 0) >= 60:
                reason_codes.append("HIGH_CONFIDENCE")
            if market_context["state"] == "GREEN":
                reason_codes.append("MARKET_GREEN")
            if attention_context["bucket"] == "STABLE":
                reason_codes.append("ATTENTION_STABLE")
        
        return QueryResult(
            ticker=ticker,
            timestamp=timestamp,
            eligible=eligible and opportunity is not None,
            reason_codes=reason_codes,
            vetoes=vetoes,
            opportunity=opportunity,
            stand_down=stand_down,
            market_context=market_context,
            attention_context=attention_context,
            calibration_context=calibration_context
        )
    
    async def _get_market_state(self) -> Dict[str, Any]:
        """Get current market state from Redis"""
        try:
            import json
            data = await self.core.redis_client.get("key:market_state")
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Error getting market state: {e}")
        return {"state": "UNKNOWN", "reason": "Unable to fetch market state"}
    
    async def _get_attention_state(self) -> Dict[str, Any]:
        """Get current attention state from Redis"""
        try:
            import json
            data = await self.core.redis_client.get("key:attention_state")
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Error getting attention state: {e}")
        return {"attention_stability_score": 50, "attention_bucket": "UNSTABLE", "degraded": True}
    
    async def _get_calibration_state(self) -> Dict[str, Any]:
        """Get current calibration state from Redis"""
        try:
            import json
            data = await self.core.redis_client.get("key:calibration_state")
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Error getting calibration state: {e}")
        return {"global_stats": {"global_shrink": 1.0}}
    
    async def _check_ticker_data(self, ticker: str) -> bool:
        """Check if we have recent data for this ticker"""
        try:
            query = """
                SELECT COUNT(*) FROM candles_5m 
                WHERE ticker = $1 AND time > NOW() - INTERVAL '24 hours'
            """
            async with self.core.db_pool.acquire() as conn:
                count = await conn.fetchval(query, ticker)
                return count > 0
        except Exception as e:
            logger.error(f"Error checking ticker data: {e}")
            return False
    
    async def _compute_opportunity(
        self, 
        ticker: str,
        market_context: Dict[str, Any],
        attention_context: Dict[str, Any],
        calibration_context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Compute opportunity for a single ticker"""
        try:
            # Fetch candles
            candles_5m = await self.core.fetch_candles(ticker, "candles_5m", limit=50)
            candles_1m = await self.core.fetch_candles(ticker, "candles_1m", limit=100)
            
            if candles_5m.empty or len(candles_5m) < 14:
                return None
            
            # Import scoring/confidence modules
            from scoring import compute_score
            from confidence import compute_confidence
            
            # Compute base score
            score_result = compute_score(candles_5m, candles_1m)
            if not score_result:
                return None
            
            score, score_components = score_result
            
            # Compute confidence
            conf_result = compute_confidence(
                score=score,
                market_state=market_context["state"],
                attention_score=attention_context["score"]
            )
            
            confidence_band, confidence_pct, why = conf_result
            
            # Apply calibration shrink
            shrink = calibration_context.get("global_shrink", 1.0)
            adjusted_confidence = confidence_pct * shrink
            
            # Determine horizon based on attention
            if attention_context["bucket"] == "CHAOTIC":
                allowed_horizons = ["H30"]
            elif attention_context["bucket"] == "UNSTABLE":
                allowed_horizons = ["H30", "H2H", "HDAY"]
            else:
                allowed_horizons = ["H30", "H2H", "HDAY", "HWEEK"]
            
            # Default horizon selection based on confidence
            if adjusted_confidence >= 60:
                horizon = "HDAY" if "HDAY" in allowed_horizons else "H2H"
            elif adjusted_confidence >= 40:
                horizon = "H2H" if "H2H" in allowed_horizons else "H30"
            else:
                horizon = "H30"
            
            # Compute ATR for targets
            atr = candles_5m['high'].tail(14).values - candles_5m['low'].tail(14).values
            atr_value = float(atr.mean()) if len(atr) > 0 else 1.0
            
            # Standard target/stop ATR multiples
            target_atr = 1.5
            stop_atr = 0.75
            
            # Probability = adjusted confidence / 100
            probability = adjusted_confidence / 100.0
            
            return {
                "ticker": ticker,
                "horizon": horizon,
                "allowed_horizons": allowed_horizons,
                "score": round(score, 2),
                "score_components": score_components,
                "confidence_band": confidence_band,
                "confidence_pct": round(confidence_pct, 2),
                "confidence_pct_adjusted": round(adjusted_confidence, 2),
                "probability": round(probability, 4),
                "target_atr": target_atr,
                "stop_atr": stop_atr,
                "atr_value": round(atr_value, 4),
                "why": why,
                "market_state": market_context["state"],
                "attention_bucket": attention_context["bucket"],
                "attention_score": attention_context["score"],
                "calibration_shrink": shrink
            }
            
        except Exception as e:
            logger.error(f"Error computing opportunity: {e}")
            return None
    
    def _build_stand_down(
        self, 
        ticker: str, 
        reason_codes: List[str], 
        vetoes: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build human-readable stand-down explanation"""
        
        explanations = {
            "MARKET_STATE_RED": "Market is in RED state - all trading halted",
            "MARKET_STATE_YELLOW": "Market is in YELLOW state - reduced confidence",
            "ATTENTION_CHAOTIC": "Market attention is CHAOTIC - only shortest horizons allowed",
            "ATTENTION_UNSTABLE": "Market attention is UNSTABLE - longer horizons gated",
            "CALIBRATION_DEGRADED": "Model calibration is degraded - probabilities reduced",
            "NO_DATA": f"No recent price data available for {ticker}",
            "LOW_CONFIDENCE": "Confidence score is below threshold",
            "LOW_PROBABILITY": "Probability of success is too low",
            "SCORING_FAILED": "Unable to compute opportunity score",
            "SCORING_ERROR": "Error during opportunity computation"
        }
        
        reasons = [explanations.get(code, code) for code in reason_codes if code in explanations]
        
        # Determine severity
        hard_vetoes = [v for v in vetoes if v.get("severity") == "HARD_VETO"]
        
        if hard_vetoes:
            action = "DO NOT TRADE"
            severity = "HARD"
        elif "LOW_CONFIDENCE" in reason_codes or "LOW_PROBABILITY" in reason_codes:
            action = "WAIT"
            severity = "SOFT"
        else:
            action = "MONITOR"
            severity = "INFO"
        
        return {
            "action": action,
            "severity": severity,
            "reasons": reasons,
            "summary": f"{ticker}: {action} - {', '.join(reasons[:2])}" if reasons else f"{ticker}: {action}"
        }
