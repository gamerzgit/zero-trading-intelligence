"""
ZERO Trading Intelligence Platform - Pydantic Schemas
Version: 1.0
Last Updated: 2026-01-11

All message schemas for Redis Pub/Sub, HTTP API, and internal communication.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


# ============================================================================
# BASE SCHEMA (All schemas inherit these fields)
# ============================================================================

class BaseSchema(BaseModel):
    """Base schema with version and timestamp"""
    schema_version: str = Field(default="1.0", description="Schema version")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="ISO 8601 timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# ============================================================================
# LEVEL 0: MARKET PERMISSION STATE
# ============================================================================

class MarketState(BaseSchema):
    """Level 0: Market Permission State (Veto Only)"""
    state: Literal["GREEN", "YELLOW", "RED"] = Field(..., description="Market permission state")
    vix_level: Optional[float] = Field(None, description="VIX level")
    vix_roc: Optional[float] = Field(None, description="VIX rate of change")
    adv_decl: Optional[float] = Field(None, description="Advance/Decline ratio")
    trin: Optional[float] = Field(None, description="TRIN (Trading Index)")
    breadth_score: Optional[float] = Field(None, description="Market breadth score")
    event_risk: bool = Field(default=False, description="Event risk flag")
    reason: Optional[str] = Field(None, description="Human-readable reason for state")


class StateChangeNotification(BaseSchema):
    """State change notification (not full state)"""
    changed_fields: List[str] = Field(..., description="List of fields that changed")
    state_key: str = Field(..., description="Redis key where full state is stored (e.g., 'key:market_state')")


# ============================================================================
# LEVEL 1: ATTENTION & NARRATIVE
# ============================================================================

class AttentionState(BaseSchema):
    """Level 1: Attention State (Non-LLM)"""
    dominant_sectors: Optional[List[Dict[str, Any]]] = Field(None, description="Array of dominant sectors with scores")
    attention_concentration: Optional[float] = Field(None, ge=0, le=100, description="0-100 concentration score")
    attention_stability_score: float = Field(..., ge=0, le=100, description="0-100 stability score (score-based, not discrete)")
    attention_bucket: Optional[Literal["STABLE", "UNSTABLE", "CHAOTIC"]] = Field(
        None, 
        description="Derived bucket: STABLE (>=70), UNSTABLE (40-69), CHAOTIC (<40) - for convenience only"
    )
    risk_on_off_state: Optional[Literal["RISK_ON", "RISK_OFF", "NEUTRAL"]] = Field(None, description="Risk-on/off state")
    correlation_regime: Optional[str] = Field(None, description="Correlation regime description")


class NarrativeState(BaseSchema):
    """Level 1: Narrative State (LLM Output)"""
    theme: str = Field(..., description="Dominant market theme")
    drivers: List[str] = Field(..., description="Key drivers identified")
    impact_relevance_to_equities: float = Field(..., ge=0, le=100, description="0-100 relevance score")
    time_horizon_bias: Literal["H30", "H2H", "HDAY", "HWEEK"] = Field(..., description="Time horizon bias")
    noise_flag: bool = Field(default=False, description="Whether this is noise")


# ============================================================================
# LEVEL 2: OPPORTUNITY DISCOVERY
# ============================================================================

class CandidateList(BaseSchema):
    """Level 2: Scanner Output (Active Candidates)"""
    candidates: List[str] = Field(..., description="List of ticker symbols")
    horizon: Literal["H30", "H2H", "HDAY", "HWEEK"] = Field(..., description="Time horizon")
    scan_time: datetime = Field(..., description="When scan was performed")
    filter_stats: Optional[Dict[str, Any]] = Field(None, description="Filter statistics (volume, spread, etc.)")


# ============================================================================
# LEVEL 3: OPPORTUNITY RANKING
# ============================================================================

class Opportunity(BaseSchema):
    """Level 3: Opportunity (Probabilistic Scoring)"""
    ticker: str = Field(..., description="Stock symbol")
    horizon: Literal["H30", "H2H", "HDAY", "HWEEK"] = Field(..., description="Time horizon")
    opportunity_score: float = Field(..., ge=0, le=100, description="0-100 opportunity score")
    probability: float = Field(..., ge=0.0, le=1.0, description="P(MFE >= Target_ATR before MAE >= Stop_ATR within horizon H)")
    target_atr: float = Field(..., description="Target excursion in ATR")
    stop_atr: float = Field(..., description="Stop excursion in ATR")
    market_state: Literal["GREEN", "YELLOW", "RED"] = Field(..., description="Market state at issue time")
    attention_stability_score: float = Field(..., ge=0, le=100, description="Attention stability score (0-100)")
    attention_bucket: Optional[Literal["STABLE", "UNSTABLE", "CHAOTIC"]] = Field(None, description="Derived bucket")
    attention_alignment: Optional[float] = Field(None, ge=0, le=100, description="0-100 alignment score")
    regime_dependency: Optional[Dict[str, Any]] = Field(None, description="Required market states")
    key_levels: Optional[Dict[str, Any]] = Field(None, description="VWAP, support, resistance levels")
    invalidation_rule: Optional[str] = Field(None, description="Invalidation conditions")
    why: Optional[List[str]] = Field(None, description="Explanation list")
    liquidity_grade: Optional[str] = Field(None, description="Liquidity assessment")


class OpportunityRank(BaseSchema):
    """Top-N Ranked Opportunities"""
    horizon: Literal["H30", "H2H", "HDAY", "HWEEK"] = Field(..., description="Time horizon")
    opportunities: List[Opportunity] = Field(..., description="Ranked list of opportunities")
    rank_time: datetime = Field(..., description="When ranking was performed")
    total_candidates: int = Field(..., description="Total candidates considered")


# ============================================================================
# LEVEL 4: TIMING & URGENCY
# ============================================================================

class UrgencyFlags(BaseSchema):
    """Level 4: Timing & Urgency Flags"""
    ticker: Optional[str] = Field(None, description="Ticker (if ticker-specific)")
    urgency: Literal["NOW", "WATCH", "DEFER"] = Field(..., description="Urgency level")
    reason: str = Field(..., description="Short reason")
    vwap_interaction: Optional[bool] = Field(None, description="VWAP interaction detected")
    volatility_shift: Optional[bool] = Field(None, description="Volatility regime transition")
    liquidity_shift: Optional[bool] = Field(None, description="Liquidity shift detected")
    session_phase: Optional[str] = Field(None, description="Session phase (open/lunch/close)")


# ============================================================================
# LEVEL 6: EXECUTION (Paper Only, Opt-In)
# ============================================================================

class TradeUpdate(BaseSchema):
    """Execution event (trade placement result)"""
    execution_id: str = Field(..., description="Deterministic execution ID for idempotency")
    ticker: Optional[str] = Field(None, description="Stock symbol")
    horizon: Optional[Literal["H30", "H2H", "HDAY", "HWEEK"]] = Field(None, description="Time horizon")
    probability: Optional[float] = Field(None, ge=0.0, le=1.0, description="Opportunity probability")
    opportunity_score: Optional[float] = Field(None, ge=0, le=100, description="Opportunity score")
    status: Literal["SUBMITTED", "BLOCKED", "SKIPPED", "REJECTED", "ERROR"] = Field(..., description="Execution status")
    alpaca_order_id: Optional[str] = Field(None, description="Alpaca order ID if submitted")
    market_state: Optional[Dict[str, Any]] = Field(None, description="Market state snapshot at execution time")
    why: Optional[List[str]] = Field(None, description="Array of reason strings")
    submitted_at: datetime = Field(..., description="When execution was attempted")


# ============================================================================
# STAND-DOWN SIGNALS
# ============================================================================

class StandDownReason(BaseSchema):
    """Stand-Down Signal (Do Not Trade)"""
    reason: str = Field(..., description="Reason for stand-down")
    scope: Literal["GLOBAL", "SECTOR", "TICKER"] = Field(..., description="Scope of stand-down")
    ticker: Optional[str] = Field(None, description="Ticker (if scope is TICKER)")
    sector: Optional[str] = Field(None, description="Sector (if scope is SECTOR)")
    expires_at: Optional[datetime] = Field(None, description="When stand-down expires")


# ============================================================================
# MARKET DATA STREAMS
# ============================================================================

class TickerUpdate(BaseSchema):
    """Ticker price/volume update"""
    ticker: str = Field(..., description="Stock symbol")
    price: float = Field(..., description="Last trade price")
    volume: int = Field(..., description="Trade volume")
    time: datetime = Field(..., description="Trade timestamp")
    bid: Optional[float] = Field(None, description="Best bid price")
    ask: Optional[float] = Field(None, description="Best ask price")
    spread: Optional[float] = Field(None, description="Ask - Bid spread")


class IndexUpdate(BaseSchema):
    """Index (SPY/QQQ/IWM) update"""
    index: str = Field(..., description="Index symbol (SPY, QQQ, IWM)")
    price: float = Field(..., description="Index price")
    volume: int = Field(..., description="Index volume")
    time: datetime = Field(..., description="Update timestamp")


class VolatilityUpdate(BaseSchema):
    """Volatility (VIX) update"""
    vix_level: float = Field(..., description="VIX level")
    vix_roc: Optional[float] = Field(None, description="VIX rate of change")
    time: datetime = Field(..., description="Update timestamp")


# ============================================================================
# NEWS & EVENTS
# ============================================================================

class NewsRaw(BaseSchema):
    """Raw news headline/article"""
    headline: str = Field(..., description="News headline")
    source: str = Field(..., description="News source")
    url: Optional[str] = Field(None, description="Article URL")
    published_at: datetime = Field(..., description="Publication timestamp")
    tickers: Optional[List[str]] = Field(None, description="Related tickers")
    sectors: Optional[List[str]] = Field(None, description="Related sectors")


class EventAlert(BaseSchema):
    """Economic event/earnings alert"""
    event_type: Literal["ECONOMIC", "EARNINGS", "FOMC", "CPI", "NFP", "OTHER"] = Field(..., description="Event type")
    name: str = Field(..., description="Event name")
    scheduled_time: datetime = Field(..., description="Scheduled event time")
    tickers: Optional[List[str]] = Field(None, description="Related tickers")
    impact_level: Optional[Literal["LOW", "MEDIUM", "HIGH"]] = Field(None, description="Expected impact level")


# ============================================================================
# QUERY MODE (HTTP API)
# ============================================================================

class QueryRequest(BaseSchema):
    """Query Mode Request"""
    ticker: str = Field(..., description="Ticker symbol to query")
    horizons: Optional[List[Literal["H30", "H2H", "HDAY", "HWEEK"]]] = Field(
        None, 
        description="Specific horizons to analyze (default: all)"
    )


class QueryResponse(BaseSchema):
    """Query Mode Response"""
    ticker: str = Field(..., description="Ticker symbol")
    eligible: bool = Field(..., description="Whether ticker is eligible for trading")
    reason_codes: Optional[List[str]] = Field(None, description="Reason codes if not eligible (liquidity fail, regime veto, etc.)")
    in_top_opportunities: bool = Field(..., description="Whether ticker is in top opportunities")
    why_not_ranked: Optional[str] = Field(None, description="Explanation if not in top opportunities")
    market_state: MarketState = Field(..., description="Current market state")
    attention_state: AttentionState = Field(..., description="Current attention state")
    narrative_state: Optional[NarrativeState] = Field(None, description="Current narrative state")
    opportunities: List[Opportunity] = Field(..., description="Opportunities by horizon")
    stand_down: Optional[StandDownReason] = Field(None, description="Stand-down reason if applicable")


# ============================================================================
# HEALTH & MONITORING
# ============================================================================

class HealthCheck(BaseSchema):
    """Service health check"""
    service: str = Field(..., description="Service name")
    status: Literal["healthy", "degraded", "unhealthy"] = Field(..., description="Health status")
    uptime_seconds: Optional[float] = Field(None, description="Service uptime in seconds")
    last_update: datetime = Field(..., description="Last update timestamp")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional health details")

