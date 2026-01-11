# Milestone 2: Regime Engine - ZERO-Native Build Prompt

**For Cursor AI - Copy/Paste Ready**

---

## 🚨 CRITICAL: BRANDING ENFORCEMENT

**STRICTLY FORBIDDEN:**
- ❌ "ELVA" (any reference)
- ❌ "Anderson" or "Anderson Zone"
- ❌ "Pine Script" (as named concept)
- ❌ "Neural Brain"
- ❌ Any external system references

**MANDATORY:**
- ✅ Use "Prime Window" (not Anderson Zone)
- ✅ Use "ZERO Core" (not ELVA)
- ✅ Use "Probability Engine" (not Neural Brain)
- ✅ All naming must be ZERO-native

---

## 📋 CONTEXT

**Project:** ZERO Trading Intelligence Platform  
**Milestone:** 2 - Market Regime Engine (Level 0)  
**Status:** Starting now  
**Previous:** Milestone 0 (Architecture) ✅ | Milestone 1 (Ingestion) ✅

**References:**
- `@docs/SPEC_LOCK.md` - Constitution (frozen)
- `@contracts/schemas.py` - Pydantic models
- `@contracts/redis_keys.md` - Redis contracts
- `@contracts/db_schema.md` - Database schema

---

## 🎯 OBJECTIVE

Build the `zero-regime` service that determines **Market Permission** (Level 0).

This is the **VETO layer** - it can halt everything, but never approve alone.

---

## 📐 ZERO PROPRIETARY LOGIC

### 1. VIX Regime Classification

Classify market volatility state:

```python
# ZERO Regime States
CALM: VIX < 15
NORMAL: VIX 15-20
ELEVATED: VIX 20-25
FEAR: VIX 25-30
PANIC: VIX > 30
```

**Data Source:** VIXY ETF (proxy for VIX) via Alpaca API

### 2. Time Regime Classification (ET Timezone)

Classify time-of-day windows:

```python
# ZERO Time Windows
OPENING: 09:30-10:30 ET (High volatility, choppy)
LUNCH: 11:00-13:00 ET (Low volume, avoid)
PRIME_WINDOW: 13:00-15:00 ET (Optimal liquidity period)
CLOSING: 15:00-16:00 ET (Gamma/closing flows)
OFF_HOURS: Market closed
```

**Note:** "Prime Window" is ZERO's proprietary term for the optimal execution window.

### 3. Market Permission Logic (MarketState)

Output: `GREEN` | `YELLOW` | `RED`

**RED (Halt - No Opportunities):**
- VIX >= 25 (FEAR or PANIC)
- Market is OFF_HOURS
- Major event risk (earnings, FOMC, etc.)

**YELLOW (Caution - Limited Horizons):**
- Time is OPENING or LUNCH
- VIX is ELEVATED (20-25)
- Minor event risk

**GREEN (Full Permission):**
- Time is PRIME_WINDOW or CLOSING
- VIX < 20 (NORMAL or CALM)
- No event risk

---

## 🏗️ IMPLEMENTATION REQUIREMENTS

### Service Structure

```
services/regime/
├── main.py              # Service entry point
├── logic.py             # RegimeCalculator class
├── vix_fetcher.py       # VIX data fetching (VIXY proxy)
├── time_detector.py     # Time window detection
├── event_calendar.py    # Event risk detection (future)
└── Dockerfile           # ARM64 compatible
```

### Core Components

#### 1. `RegimeCalculator` (logic.py)

```python
class RegimeCalculator:
    """
    ZERO Regime Calculator - Determines Market Permission
    
    This is Level 0 (Veto Layer) - can halt, never approve alone.
    """
    
    def calculate_market_state(
        self,
        vix_level: float,
        current_time: datetime,
        event_risk: Optional[str] = None
    ) -> MarketState:
        """
        Calculate MarketState (GREEN/YELLOW/RED)
        
        Returns:
            MarketState with reasoning
        """
        pass
    
    def get_vix_regime(self, vix_level: float) -> str:
        """Classify VIX regime"""
        pass
    
    def get_time_regime(self, current_time: datetime) -> str:
        """Classify time window (PRIME_WINDOW, etc.)"""
        pass
```

#### 2. `VIXFetcher` (vix_fetcher.py)

```python
class VIXFetcher:
    """
    Fetch VIX level using VIXY ETF as proxy
    """
    
    async def fetch_current_vix(self) -> Optional[float]:
        """
        Fetch VIX estimate from VIXY ETF
        
        Returns:
            VIX level (estimated) or None if unavailable
        """
        pass
```

#### 3. Main Service (main.py)

**Requirements:**
- Run as long-lived async process
- Update every 1 minute
- Publish state changes to Redis
- Persist to TimescaleDB
- Expose `/health` endpoint

**Redis Events:**
- Publish to `chan:market_state_changed` when state changes
- Store current state in `key:market_state`

**Database:**
- Write to `regime_log` table on state changes

---

## 📊 OUTPUT SCHEMA

### MarketState (Pydantic Model)

```python
class MarketState(BaseModel):
    state: Literal["GREEN", "YELLOW", "RED"]
    vix_regime: str  # CALM, NORMAL, ELEVATED, FEAR, PANIC
    time_regime: str  # OPENING, LUNCH, PRIME_WINDOW, CLOSING, OFF_HOURS
    vix_level: float
    reasoning: str  # Human-readable explanation
    timestamp: datetime
    schema_version: str = "1.0"
```

### Example Output

```json
{
  "state": "GREEN",
  "vix_regime": "NORMAL",
  "time_regime": "PRIME_WINDOW",
  "vix_level": 16.5,
  "reasoning": "Market is in Prime Window with Normal VIX. Full permission granted.",
  "timestamp": "2026-01-11T18:00:00Z",
  "schema_version": "1.0"
}
```

---

## 🐳 DOCKER INTEGRATION

### Update `infra/docker-compose.yml`

Add service:

```yaml
zero-regime:
  build:
    context: ..
    dockerfile: services/regime/Dockerfile
  container_name: zero-regime
  environment:
    DB_HOST: ${DB_HOST:-timescaledb}
    DB_PORT: ${DB_PORT:-5432}
    DB_NAME: ${DB_NAME:-zero_trading}
    DB_USER: ${DB_USER:-zero_user}
    DB_PASSWORD: ${DB_PASSWORD}
    REDIS_HOST: ${REDIS_HOST:-redis}
    REDIS_PORT: ${REDIS_PORT:-6379}
    ALPACA_API_KEY: ${ALPACA_API_KEY}
    ALPACA_SECRET_KEY: ${ALPACA_SECRET_KEY}
  depends_on:
    timescaledb:
      condition: service_healthy
    redis:
      condition: service_healthy
  restart: unless-stopped
  networks:
    - zero-network
```

---

## ✅ ACCEPTANCE CRITERIA

1. **Service runs continuously**
   - Updates every 1 minute
   - Handles errors gracefully
   - Auto-reconnects on failures

2. **Correct state calculation**
   - RED when VIX >= 25 or market closed
   - YELLOW when OPENING/LUNCH or ELEVATED VIX
   - GREEN when PRIME_WINDOW/CLOSING + low VIX

3. **Redis integration**
   - Publishes to `chan:market_state_changed` on changes
   - Stores in `key:market_state`

4. **Database persistence**
   - Writes to `regime_log` table
   - Includes all state fields

5. **Health endpoint**
   - `GET /health` returns service status
   - Includes current MarketState

6. **ZERO-native naming**
   - No external references
   - Uses "Prime Window" terminology
   - All comments use ZERO vocabulary

---

## 🚫 WHAT NOT TO BUILD

- ❌ Do NOT build event calendar yet (Milestone 3+)
- ❌ Do NOT build attention engine (Milestone 3)
- ❌ Do NOT build scanner (Milestone 4)
- ❌ Do NOT build probability engine (Milestone 5)

**This milestone ONLY builds the Veto Layer (Level 0).**

---

## 📝 DELIVERABLES

1. `services/regime/` - Full service implementation
2. Updated `infra/docker-compose.yml`
3. Updated `contracts/schemas.py` (if MarketState model needed)
4. Service README explaining the logic

---

## 🎯 SUCCESS METRIC

**You know it works when:**
- Service runs 24/7 without crashing
- State changes are published to Redis
- Database shows regime_log entries
- Health endpoint returns current state
- State correctly reflects market conditions

---

**Remember: This is ZERO's proprietary Regime Engine. It speaks ZERO's language.**

