# Audit Fixes Applied - 2026-01-14

## Critical Fixes

### 1. ✅ VIX/Volatility Logic Fixed

**Problem:** System was showing RED even during market open because VIXY→VIX conversion was producing incorrect values (~40, causing false volatility halts).

**Solution:**
- **Removed VIX conversion** - Use VIXY price directly
- **Adjusted thresholds for VIXY price levels:**
  - GREEN: VIXY < $20 (normal/low vol)
  - YELLOW: VIXY $20-25 (elevated vol)
  - RED: VIXY >= $25 (high vol/panic)
- **Updated reason text** to clearly show "VIXY=$X.XX" instead of "VIX≈X"

**Files Changed:**
- `services/regime/vol_proxy.py` - Returns VIXY price directly (no conversion)
- `services/regime/logic.py` - Uses VIXY-based thresholds

**Impact:** MarketState should now correctly show GREEN during normal market conditions.

---

### 2. ✅ SPEC_LOCK Addendum Added

**Problem:** SPEC_LOCK says "NOT a trading bot" but Milestone 6 is an execution engine.

**Solution:** Added explicit addendum (Section 0.1) clarifying:
- Execution Engine is OPTIONAL and NOT required for ZERO Intelligence compliance
- Execution MUST be hard-disabled unless `ALPACA_PAPER=true` AND `key:execution_enabled=true`
- Execution is paper-only by default
- Intelligence Platform (Milestones 0-5) remains valid without execution

**Files Changed:**
- `docs/SPEC_LOCK.md` - Added Section 0.1 "Execution Engine Addendum"

---

### 3. ✅ Schemas.py Audit Fixes

**A) Timestamp Timezone-Aware** ✅
- Already fixed: `timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))`
- All timestamps are timezone-aware UTC

**B) Pydantic v2 Compatibility** ✅
- Added comment explaining v1 style is kept for backward compatibility
- Noted that v2 would use `model_config` instead
- Current code works with both v1 and v2

**C) TradeUpdate.market_state** ✅
- Already correctly typed: `market_state: Optional[MarketState]` (not Dict)
- Provides validation and prevents schema drift

**D) chan:opportunity_update Payload** ✅
- Documented in `contracts/redis_keys.md` as `OpportunityRank` schema
- Matches implementation in `services/core/main.py`

**Files Changed:**
- `contracts/schemas.py` - Added Pydantic v2 compatibility comment

---

## File Structure Verification

### Contracts / Spec
- ✅ `docs/SPEC_LOCK.md` - Constitution (updated with addendum)
- ✅ `contracts/schemas.py` - All Pydantic schemas
- ✅ `contracts/redis_keys.md` - Redis contracts
- ✅ `contracts/db_schema.md` - Database schema
- ✅ `contracts/api_contract.md` - API contracts

### Infrastructure
- ✅ `infra/docker-compose.yml` - All services defined
- ✅ `infra/db/init.sql` - Database initialization
- ✅ `infra/db/migrations/001_add_execution_log.sql` - Execution log table
- ✅ `infra/grafana/provisioning/` - Grafana configs

### Services
- ✅ `services/ingest/` - Price ingestion (Milestone 1)
- ✅ `services/regime/` - Market state engine (Milestone 2)
- ✅ `services/scanner/` - Opportunity discovery (Milestone 3)
- ✅ `services/core/` - Opportunity ranking (Milestone 4)
- ✅ `services/dashboard/` - Streamlit UI (Milestone 5)
- ✅ `services/execution/` - Execution gateway (Milestone 6)

---

## Next Steps

### Immediate (Before Milestone 7)

1. **Test VIXY Thresholds:**
   ```bash
   # On Jetson, during market hours:
   docker compose --env-file .env -f infra/docker-compose.yml exec redis redis-cli GET key:market_state | jq .
   ```
   Should show GREEN if VIXY < $20

2. **Verify MarketState Flow:**
   - Regime → Scanner → Core → Execution
   - All services should respect MarketState RED/YELLOW/GREEN

### Milestone 7: Truth Test + Calibration

**Requirements:**
- Daily truth test after market close
- Compute realized MFE/MAE for each opportunity
- Store to `performance_log` table
- Track calibration by horizon/regime/attention bucket
- Degrade confidence when miscalibrated

**Database Schema Needed:**
- `performance_log` table (to be created in Milestone 7)

---

## Verification Checklist

- [x] VIXY thresholds adjusted for direct price levels
- [x] SPEC_LOCK addendum added for execution engine
- [x] Timestamps are timezone-aware UTC
- [x] TradeUpdate.market_state is typed as MarketState
- [x] chan:opportunity_update payload matches OpportunityRank schema
- [x] File structure verified
- [ ] MarketState shows GREEN during normal market hours (test on Jetson)
- [ ] All services respect MarketState veto (test on Jetson)

---

**Status:** Ready for testing on Jetson. Pull latest changes and rebuild regime service.
