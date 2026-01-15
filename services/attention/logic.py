"""
ZERO Attention Engine - Core Logic

Computes AttentionState (score-based 0-100) measuring market stability.
Thresholds per SPEC_LOCK:
- STABLE: score >= 70
- UNSTABLE: score 40-69
- CHAOTIC: score < 40
"""

import logging
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
from collections import deque

logger = logging.getLogger(__name__)

# Symbols for attention computation
INDEX_PROXIES = ["SPY", "QQQ", "IWM"]
VOL_PROXY = "VIXY"
SECTOR_PROXIES = ["XLF", "XLK", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLC"]

# Thresholds per SPEC_LOCK
STABLE_THRESHOLD = 70
UNSTABLE_THRESHOLD = 40

# Component weights for stability score
WEIGHTS = {
    "leadership_churn": 0.25,
    "index_dispersion": 0.30,
    "volatility_pressure": 0.25,
    "correlation_regime": 0.20
}


class AttentionCalculator:
    """
    Computes AttentionState from market data.
    
    Components:
    1. Dominant Sectors (leaderboard)
    2. Attention Concentration (0-100)
    3. Attention Stability Score (0-100)
    4. Risk On/Off State
    5. Correlation Regime
    """
    
    def __init__(self):
        # Track leadership history for churn calculation
        self.leadership_history: deque = deque(maxlen=12)  # ~1 hour of 5m intervals
        self.last_top3: List[str] = []
    
    def compute_returns(
        self, 
        candles: List[Dict[str, Any]], 
        periods: int = 12  # 60 min for 5m candles
    ) -> Optional[float]:
        """Compute return over N periods"""
        if not candles or len(candles) < 2:
            return None
        
        # Use last N candles
        recent = candles[-min(periods, len(candles)):]
        if len(recent) < 2:
            return None
        
        start_price = float(recent[0]['close'])
        end_price = float(recent[-1]['close'])
        
        if start_price <= 0:
            return None
        
        return (end_price - start_price) / start_price
    
    def compute_dominant_sectors(
        self, 
        sector_candles: Dict[str, List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """
        Compute 30-60 minute returns for each sector proxy.
        Return top 3 as dominant sectors.
        """
        sector_returns = []
        
        for symbol, candles in sector_candles.items():
            if symbol in SECTOR_PROXIES:
                ret = self.compute_returns(candles, periods=12)  # ~60 min
                if ret is not None:
                    sector_returns.append({
                        "symbol": symbol,
                        "return": round(ret * 100, 4),  # As percentage
                        "abs_return": abs(ret)
                    })
        
        # Sort by absolute return (leadership = biggest movers)
        sector_returns.sort(key=lambda x: x["abs_return"], reverse=True)
        
        # Top 3 with rank
        dominant = []
        for i, sr in enumerate(sector_returns[:3]):
            dominant.append({
                "symbol": sr["symbol"],
                "return": sr["return"],
                "rank": i + 1
            })
        
        return dominant
    
    def compute_attention_concentration(
        self, 
        sector_candles: Dict[str, List[Dict[str, Any]]]
    ) -> float:
        """
        Compute Herfindahl-style concentration from sector absolute returns.
        0 = perfectly broad, 100 = extremely concentrated
        """
        abs_returns = []
        
        for symbol, candles in sector_candles.items():
            if symbol in SECTOR_PROXIES:
                ret = self.compute_returns(candles, periods=12)
                if ret is not None:
                    abs_returns.append(abs(ret))
        
        if not abs_returns or sum(abs_returns) == 0:
            return 50.0  # Neutral if no data
        
        # Normalize to shares
        total = sum(abs_returns)
        shares = [r / total for r in abs_returns]
        
        # Herfindahl index (sum of squared shares)
        hhi = sum(s ** 2 for s in shares)
        
        # Normalize: min HHI = 1/N (perfectly equal), max = 1 (one dominates)
        n = len(shares)
        min_hhi = 1 / n if n > 0 else 0
        
        # Scale to 0-100
        if hhi <= min_hhi:
            concentration = 0.0
        else:
            concentration = ((hhi - min_hhi) / (1 - min_hhi)) * 100
        
        return round(min(100, max(0, concentration)), 2)
    
    def compute_leadership_churn(
        self, 
        dominant_sectors: List[Dict[str, Any]]
    ) -> float:
        """
        Compute how often top-3 sectors change.
        Returns score 0-100 where 100 = stable leadership, 0 = chaotic churn
        """
        current_top3 = [s["symbol"] for s in dominant_sectors[:3]]
        
        if not self.last_top3:
            self.last_top3 = current_top3
            return 80.0  # First run, assume stable
        
        # Count how many of current top3 were in previous top3
        overlap = len(set(current_top3) & set(self.last_top3))
        
        # Track history
        self.leadership_history.append(overlap)
        self.last_top3 = current_top3
        
        # Average overlap over history
        if self.leadership_history:
            avg_overlap = sum(self.leadership_history) / len(self.leadership_history)
            # 3 = perfect stability (100), 0 = total churn (0)
            stability = (avg_overlap / 3) * 100
            return round(stability, 2)
        
        return 50.0
    
    def compute_index_dispersion(
        self, 
        index_candles: Dict[str, List[Dict[str, Any]]]
    ) -> float:
        """
        Compute divergence between SPY/QQQ/IWM returns.
        Returns score 0-100 where 100 = aligned, 0 = highly divergent
        """
        returns = []
        
        for symbol in INDEX_PROXIES:
            if symbol in index_candles:
                ret = self.compute_returns(index_candles[symbol], periods=12)
                if ret is not None:
                    returns.append(ret)
        
        if len(returns) < 2:
            return 50.0  # Neutral if insufficient data
        
        # Standard deviation of returns
        std_dev = np.std(returns)
        
        # Typical range: 0 (perfect alignment) to ~0.02 (2% divergence)
        # Scale inversely: low divergence = high score
        max_divergence = 0.02
        divergence_ratio = min(std_dev / max_divergence, 1.0)
        
        alignment_score = (1 - divergence_ratio) * 100
        return round(alignment_score, 2)
    
    def compute_volatility_pressure(
        self, 
        vixy_candles: List[Dict[str, Any]],
        market_state: str
    ) -> float:
        """
        Compute volatility pressure score.
        Returns 0-100 where 100 = calm, 0 = high pressure
        """
        base_score = 70.0
        
        # Penalize for YELLOW/RED market state
        if market_state == "RED":
            base_score -= 40
        elif market_state == "YELLOW":
            base_score -= 20
        
        # Check VIXY trend
        if vixy_candles and len(vixy_candles) >= 2:
            vixy_return = self.compute_returns(vixy_candles, periods=6)  # 30 min
            if vixy_return is not None:
                # VIXY up = volatility rising = pressure
                if vixy_return > 0.02:  # >2% rise
                    base_score -= 30
                elif vixy_return > 0.01:  # >1% rise
                    base_score -= 15
                elif vixy_return < -0.01:  # Falling = calm
                    base_score += 10
        
        return round(min(100, max(0, base_score)), 2)
    
    def compute_correlation_score(
        self, 
        index_candles: Dict[str, List[Dict[str, Any]]]
    ) -> Tuple[float, str]:
        """
        Compute rolling correlation among SPY/QQQ/IWM.
        Returns (score 0-100, regime_string)
        
        Very high correlation + large moves = risk event (penalize)
        Moderate correlation + orderly = stable
        """
        # Get close prices for each index
        prices = {}
        for symbol in INDEX_PROXIES:
            if symbol in index_candles and index_candles[symbol]:
                prices[symbol] = [float(c['close']) for c in index_candles[symbol]]
        
        if len(prices) < 2:
            return 50.0, "Insufficient Data"
        
        # Compute returns
        returns = {}
        for symbol, price_list in prices.items():
            if len(price_list) >= 2:
                rets = [(price_list[i] - price_list[i-1]) / price_list[i-1] 
                        for i in range(1, len(price_list))]
                returns[symbol] = rets
        
        if len(returns) < 2:
            return 50.0, "Insufficient Data"
        
        # Compute pairwise correlations
        correlations = []
        symbols = list(returns.keys())
        for i in range(len(symbols)):
            for j in range(i + 1, len(symbols)):
                r1 = returns[symbols[i]]
                r2 = returns[symbols[j]]
                min_len = min(len(r1), len(r2))
                if min_len >= 5:
                    corr = np.corrcoef(r1[:min_len], r2[:min_len])[0, 1]
                    if not np.isnan(corr):
                        correlations.append(corr)
        
        if not correlations:
            return 50.0, "Normal Correlation"
        
        avg_corr = np.mean(correlations)
        
        # Determine regime
        if avg_corr > 0.9:
            regime = "High Correlation / Risk-Off"
            score = 40.0  # High correlation often means risk event
        elif avg_corr > 0.7:
            regime = "Elevated Correlation"
            score = 60.0
        elif avg_corr > 0.4:
            regime = "Normal Correlation"
            score = 80.0
        elif avg_corr > 0.1:
            regime = "Fragmented Leadership"
            score = 60.0
        else:
            regime = "Decorrelated / Rotation"
            score = 50.0
        
        return round(score, 2), regime
    
    def compute_risk_on_off_state(
        self,
        index_candles: Dict[str, List[Dict[str, Any]]],
        vixy_candles: List[Dict[str, Any]],
        correlation_score: float
    ) -> str:
        """
        Determine RISK_ON / RISK_OFF / NEUTRAL state.
        
        RISK_OFF: IWM underperforms + correlation high + vol elevated
        RISK_ON: IWM outperforming + vol calm
        """
        # Get IWM vs SPY relative performance
        iwm_ret = self.compute_returns(index_candles.get("IWM", []), periods=12)
        spy_ret = self.compute_returns(index_candles.get("SPY", []), periods=12)
        vixy_ret = self.compute_returns(vixy_candles, periods=6)
        
        if iwm_ret is None or spy_ret is None:
            return "NEUTRAL"
        
        iwm_relative = iwm_ret - spy_ret
        vol_elevated = vixy_ret is not None and vixy_ret > 0.01
        
        # RISK_OFF conditions
        if iwm_relative < -0.005 and correlation_score < 50 and vol_elevated:
            return "RISK_OFF"
        
        # RISK_ON conditions
        if iwm_relative > 0.003 and (vixy_ret is None or vixy_ret < 0):
            return "RISK_ON"
        
        return "NEUTRAL"
    
    def compute_attention_state(
        self,
        all_candles: Dict[str, List[Dict[str, Any]]],
        market_state: str = "GREEN"
    ) -> Dict[str, Any]:
        """
        Compute full AttentionState.
        
        Returns dict matching AttentionState schema.
        """
        now = datetime.now(timezone.utc)
        
        # Separate candles by type
        index_candles = {s: all_candles.get(s, []) for s in INDEX_PROXIES}
        sector_candles = {s: all_candles.get(s, []) for s in SECTOR_PROXIES if s in all_candles}
        vixy_candles = all_candles.get(VOL_PROXY, [])
        
        # Check if we have minimum data
        available_indices = sum(1 for s in INDEX_PROXIES if all_candles.get(s))
        available_sectors = sum(1 for s in SECTOR_PROXIES if all_candles.get(s))
        
        if available_indices < 2:
            logger.warning(f"Insufficient index data ({available_indices}/3), using degraded state")
            return self._degraded_state("Insufficient index data")
        
        try:
            # 1. Dominant Sectors
            dominant_sectors = self.compute_dominant_sectors(sector_candles)
            
            # 2. Attention Concentration
            attention_concentration = self.compute_attention_concentration(sector_candles)
            
            # 3. Component scores for stability
            leadership_score = self.compute_leadership_churn(dominant_sectors)
            dispersion_score = self.compute_index_dispersion(index_candles)
            volatility_score = self.compute_volatility_pressure(vixy_candles, market_state)
            correlation_score, correlation_regime = self.compute_correlation_score(index_candles)
            
            # 4. Weighted stability score
            attention_stability_score = (
                WEIGHTS["leadership_churn"] * leadership_score +
                WEIGHTS["index_dispersion"] * dispersion_score +
                WEIGHTS["volatility_pressure"] * volatility_score +
                WEIGHTS["correlation_regime"] * correlation_score
            )
            attention_stability_score = round(min(100, max(0, attention_stability_score)), 2)
            
            # 5. Derive bucket
            if attention_stability_score >= STABLE_THRESHOLD:
                attention_bucket = "STABLE"
            elif attention_stability_score >= UNSTABLE_THRESHOLD:
                attention_bucket = "UNSTABLE"
            else:
                attention_bucket = "CHAOTIC"
            
            # 6. Risk On/Off State
            risk_on_off_state = self.compute_risk_on_off_state(
                index_candles, vixy_candles, correlation_score
            )
            
            logger.info(
                f"Attention computed: score={attention_stability_score}, bucket={attention_bucket}, "
                f"risk={risk_on_off_state}, correlation={correlation_regime}"
            )
            
            return {
                "schema_version": "1.0",
                "timestamp": now.isoformat(),
                "dominant_sectors": dominant_sectors,
                "attention_concentration": attention_concentration,
                "attention_stability_score": attention_stability_score,
                "attention_bucket": attention_bucket,
                "risk_on_off_state": risk_on_off_state,
                "correlation_regime": correlation_regime,
                "components": {
                    "leadership_score": leadership_score,
                    "dispersion_score": dispersion_score,
                    "volatility_score": volatility_score,
                    "correlation_score": correlation_score
                }
            }
            
        except Exception as e:
            logger.error(f"Error computing attention: {e}", exc_info=True)
            return self._degraded_state(f"Computation error: {str(e)}")
    
    def _degraded_state(self, reason: str) -> Dict[str, Any]:
        """Return safe degraded AttentionState per SPEC_LOCK"""
        now = datetime.now(timezone.utc)
        
        logger.warning(f"Using degraded attention state: {reason}")
        
        return {
            "schema_version": "1.0",
            "timestamp": now.isoformat(),
            "dominant_sectors": [],
            "attention_concentration": 50.0,
            "attention_stability_score": 50.0,
            "attention_bucket": "UNSTABLE",
            "risk_on_off_state": "NEUTRAL",
            "correlation_regime": "Unknown",
            "degraded": True,
            "degraded_reason": reason
        }
