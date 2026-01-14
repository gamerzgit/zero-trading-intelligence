# ZERO Platform - Specification Lock (Constitution)

**Version:** 2.0  
**Status:** FROZEN - Non-negotiable rules  
**Last Updated:** 2026-01-11

---

## 0. NON-GOALS (What ZERO Is NOT)

1. **NOT a trading bot** - ZERO does NOT execute LIVE trades by default; execution is an opt-in paper-only gateway (Milestone 6) for testing and validation purposes only
2. **NOT an automated trading system** - No entry/exit optimization for automation
3. **NOT a deterministic price predictor** - No fixed price targets
4. **NOT a guarantee system** - No claims of guaranteed outcomes
5. **NOT an HFT system** - No latency competition or high-frequency trading
6. **NOT a sentiment-only system** - Narrative ≠ sentiment

---

## 1. HIERARCHY OVERRIDES (Strict Enforcement)

### 1.1 Hierarchy Levels (Vertical Stack - Cannot Override Upward)

```
Level 0: Market Permission (VETO ONLY)
    ↓ (can veto, never approve alone)
Level 1: Attention & Narrative (Strategist)
    ↓ (gates longer horizons if unstable)
Level 2: Opportunity Discovery (Universe Scanner)
    ↓ (hard filters: liquidity, spread, volume)
Level 3: Opportunity Ranking (Probabilistic Scoring)
    ↓ (probability outputs)
Level 4: Timing & Urgency (Why Now?)
```

### 1.2 Override Rules (Hard Constraints)

- **Level 0 can VETO everything** - It can NEVER "approve" a trade by itself
- **Event risk veto** (macro releases, earnings windows) overrides timing
- **Liquidity/spread rules** override scoring (no exceptions)
- **Attention alignment** penalizes ranking and gates longer horizons if unstable
- **Lower levels CANNOT override higher levels** (strictly enforced)
- **Urgency (Level 4) is advisory only** - Cannot override MarketState, AttentionState, or Ranking score

### 1.3 Hierarchy Violation Handling

If any service attempts to override a higher level:
- Log violation with severity
- Reject the override
- Keep last-known valid state (do not change state)
- Escalate to YELLOW only if repeated violations exceed threshold (e.g., 5 violations in 1 minute)

---

## 2. PROBABILITY DEFINITION (Mandatory, Non-Negotiable)

### 2.1 Exact Definition

Probability MUST be defined as:

```
P(MFE >= Target_ATR before MAE >= Stop_ATR within horizon H)
```

Where:
- **MFE** = Max Favorable Excursion (in ATR units)
- **MAE** = Max Adverse Excursion (in ATR units)
- **Target_ATR** = Target excursion in ATR (e.g., 1.2 ATR)
- **Stop_ATR** = Stop excursion in ATR (e.g., 0.8 ATR)
- **H** = Time horizon (H30, H2H, HDAY, HWEEK)

### 2.2 Conditioning Requirements

Probability MUST be conditional on:
1. **MarketState** (Level 0) - Regime permission
2. **AttentionState** (Level 1) - Attention stability and alignment

### 2.3 Example

For H30 horizon:
```
P(MFE >= 1.2 ATR before MAE >= 0.8 ATR within 60 minutes | MarketState=GREEN, AttentionState=STABLE)
```

### 2.4 Non-Allowed Probability Definitions

- ❌ P(price > $X) - No deterministic price targets
- ❌ P(profit > Y%) - No percentage-based without ATR
- ❌ Unconditional probabilities - Must condition on MarketState + AttentionState

---

## 3. CONDITIONING REQUIREMENTS

### 3.1 MarketState Conditioning

All probability outputs MUST be conditional on MarketState:
- **GREEN**: Full probability range allowed
- **YELLOW**: Reduced probability range (penalty applied)
- **RED**: Zero probability (system halt)

### 3.2 AttentionState Conditioning

All probability outputs MUST be conditional on AttentionState stability score:
- **Score >= 70 (Stable)**: Full probability range allowed
- **Score 40-69 (Unstable)**: Penalty applied, longer horizons gated
- **Score < 40 (Chaotic)**: Significant penalty, only H30 allowed

**Note:** AttentionState uses score-based thresholds, not discrete states. Thresholds are configurable.

### 3.3 Regime Dependency

Each opportunity MUST declare:
- Which MarketState(s) it requires
- Which AttentionState(s) it requires
- Invalidation if states change

---

## 4. ACCEPTANCE CRITERIA (Definition of Done)

### 4.1 Core Functionality

System is "done" when:

- ✅ Runs 24/7 without gaps in ingestion
- ✅ Produces Morning Brief daily without manual intervention
- ✅ Produces Top 10 ranked opportunities by horizon
- ✅ Provides full analytics for any ticker via Query Mode
- ✅ Maintains performance logs with truth-test outcomes
- ✅ Automatically degrades confidence when miscalibrated
- ✅ Provides "What not to trade" guidance based on regime/event risk
- ✅ Dashboard shows all three: General view, Opportunity feed, Debug/Ops

### 4.2 Data Integrity

- ✅ Gap detection implemented (detect missing candles)
- ✅ Backfill attempt on gap detection
- ✅ Explicit gap logging to database (ingest_gap_log table)
- ✅ Retention policies enforced automatically
- ✅ Compression enabled for chunks >24h
- ✅ Redis state consistent with DB state

### 4.3 Service Reliability

- ✅ If zero-core-logic fails, zero-ingest-price continues (no gaps)
- ✅ If zero-attention fails, scanner degrades gracefully
- ✅ All services auto-restart on failure
- ✅ Health checks for all services

### 4.4 Output Quality

- ✅ All probabilities follow exact definition (MFE/MAE/ATR)
- ✅ All outputs conditioned on MarketState + AttentionState (score-based, 0-100)
- ✅ All opportunities include invalidation rules
- ✅ All recommendations include "why" explanations
- ✅ Query mode explains "why not ranked" if ticker excluded
- ✅ Stand-down signals provided when no trading recommended

---

## 5. MODE REQUIREMENTS

### 5.1 SCAN Mode (Default)

- Continuously scans configured universe (S&P 500 default)
- Generates ranked opportunities by horizon
- Updates every configurable interval (default: 60 seconds)

### 5.2 QUERY Mode (Mandatory)

- **Endpoint**: `GET /query?ticker=TSLA` (HTTP-only, NOT Redis Pub/Sub)
- Works for ANY ticker (not limited to scan universe)
- Returns same structure as scan results
- Must work even if ticker outside scan universe
- If data unavailable: explicit error with reason
- **MUST include**: `eligible` field (true/false) and `reason_codes` if not eligible
- **MUST explain**: Why ticker is/isn't in top opportunities

---

## 6. TRUTH TEST REQUIREMENTS

### 6.1 Daily Truth Test (Mandatory)

- Runs once daily after market close (4pm ET)
- For each signal/opportunity issued:
  - Compute realized MFE/MAE in its horizon window
  - Evaluate: FAIL if MAE hits stop before MFE hits target
  - Store to performance_log table

### 6.2 Confidence Degradation (Self-Preservation)

- Maintain calibration metrics by:
  - Horizon (H30, H2H, HDAY, HWEEK)
  - Regime (GREEN, YELLOW, RED)
  - Attention stability bucket
- If calibration drifts:
  - Reduce probability outputs (shrink)
  - Tighten scanner thresholds
  - Increase YELLOW/RED likelihood
  - Penalize low-stability narratives for longer horizons

---

## 7. DATA RETENTION (Non-Negotiable)

### 7.1 TimescaleDB Retention Policies

- **ticks**: DROP after 7 days
- **candles_1m**: DROP after 1 year
- **candles_5m**: KEEP FOREVER (no drop policy)
- **candles_1d**: KEEP FOREVER (no drop policy)

### 7.2 Compression

- Enable compression for chunks older than 24 hours
- Apply to all hypertables (candles_1m, candles_5m, candles_1d)

---

## 8. HARDWARE CONSTRAINTS

### 8.1 Jetson Orin AGX Requirements

- ARM64 architecture (all Docker images must be ARM64)
- JetPack 6.x
- Ubuntu 22.04 LTS
- **64GB unified memory** (not 32GB)
- 1TB NVMe mounted for data storage
- MAXN power mode (sudo nvpmodel -m 0)
- Hardwired Ethernet (WiFi disabled)

### 8.2 Storage Requirements

- **DO NOT** store DB or high-write workloads on eMMC
- All Docker volumes must mount to NVMe path: `./data_nvme/`
- Monitor disk utilization (1TB limit)

---

## 9. INTERFACE FREEZE RULES

### 9.1 Database Schema

- Table names are FROZEN (cannot change without migration)
- Column names are FROZEN (cannot change without migration)
- Indexes can be added (performance optimization)

### 9.2 Redis Contracts

- Key names are FROZEN (cannot change without migration)
- Channel names are FROZEN (cannot change without migration)
- Payload schemas are FROZEN (cannot change without migration)

### 9.3 API Contracts

- Endpoint paths are FROZEN (cannot change without versioning)
- Request/response schemas are FROZEN (cannot change without versioning)

### 9.4 JSON Schemas

- Schema version field is MANDATORY
- Timestamp field is MANDATORY
- Breaking changes require schema version bump

---

## 10. ERROR HANDLING

### 10.1 Graceful Degradation

- If data source unavailable: degrade gracefully, log error
- If service fails: other services continue (no cascade failure)
- If GPU unavailable: fall back to CPU (with performance warning)

### 10.2 Error Reporting

- All errors must be logged with:
  - Timestamp
  - Service name
  - Error type
  - Context (ticker, horizon, etc.)
  - Severity level

### 10.3 Redis Backpressure Handling

- If Redis lag/backlog detected:
  - Scanner throttles or pauses
  - Log backpressure event
  - Degrade gracefully (continue with cached state)
- Monitor Redis memory usage
- Alert if Redis memory > 80% capacity

---

## 11. VERSIONING

### 11.1 Schema Versioning

- All schemas must include `schema_version` field
- Breaking changes require major version bump
- Non-breaking changes require minor version bump

### 11.2 API Versioning

- Breaking API changes require version in path: `/v1/query`, `/v2/query`
- Non-breaking changes can be added to existing version

---

## 12. TESTING REQUIREMENTS

### 12.1 Testing Requirements (MVP Phase)

For MVP/Milestone 0-5:
- Smoke tests (basic functionality)
- Infrastructure validation (Docker, DB, Redis)
- Contract validation (schema compliance)

### 12.2 Testing Requirements (Later Milestones)

For Milestone 5+:
- Unit tests for all services
- Integration tests (data flow, Redis, DB)
- Truth test validation (MFE/MAE, calibration)
- Target: 80% code coverage

---

## 13. DOCUMENTATION REQUIREMENTS

### 13.1 Code Documentation

- All functions must have docstrings
- All classes must have docstrings
- Complex logic must have inline comments

### 13.2 API Documentation

- All endpoints must be documented
- Request/response examples required
- Error codes documented

### 13.3 Architecture Documentation

- System architecture diagram
- Data flow diagram
- Service interaction diagram

---

## 14. SECURITY REQUIREMENTS

### 14.1 API Security

- No authentication required for local access (Jetson local network)
- If exposed externally: implement authentication

### 14.2 Data Security

- API keys stored in environment variables (not in code)
- Database credentials in environment variables
- No sensitive data in logs

---

## 15. PERFORMANCE REQUIREMENTS

### 15.1 Latency Targets (Best-Effort Goals)

**Note:** These are operational targets, not hard requirements. External API latency and hardware variance may cause deviations.

- Ingestion lag: Target < 1 second
- Scanner update: Target < 5 seconds
- Query response: Target < 2 seconds
- Dashboard update: Target < 1 second

### 15.2 Resource Usage (Best-Effort Targets)

**Note:** These are operational goals, not hard requirements. External APIs and hardware variance may cause deviations.

- CPU usage: Target < 80% average
- GPU usage: Target < 90% average
- **Memory usage: Target < 48GB average (Jetson has 64GB unified memory)**
- **Avoid OOM spikes; graceful degradation required**
- Disk usage: Monitor 1TB limit

---

## 16. CHANGE CONTROL

### 16.1 Breaking Changes

- Breaking changes require:
  1. Update SPEC_LOCK.md
  2. Update schema version
  3. Migration script
  4. Documentation update

### 16.2 Non-Breaking Changes

- Can be added without SPEC_LOCK update
- Must maintain backward compatibility
- Must update documentation

---

**END OF SPEC LOCK**

This document is the "constitution" of the ZERO platform. All implementations must adhere to these rules. Violations will be rejected.

