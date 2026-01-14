# Apply Contract & Schema Improvements

**Date:** 2026-01-14  
**Commit:** `60dd7f0` - Fix contract mismatches and schema improvements

---

## Quick Steps (Jetson)

### 1. Pull Latest Changes

```bash
cd ~/zero-trading-intelligence
git pull
```

**Expected output:**
```
Updating ea8137e..60dd7f0
Fast-forward
 contracts/db_schema.md     | 33 +++++++++++++++++++++++++++++-
 contracts/redis_keys.md    |  4 ++--
 contracts/schemas.py       | 10 ++++-----
 docs/SPEC_LOCK.md          |  2 +-
 services/execution/main.py | 51 ++++++++++++++++++++++++++--------------------
 5 files changed, 69 insertions(+), 31 deletions(-)
```

---

### 2. Rebuild Affected Services

**Rebuild only `zero-execution` (main change):**

```bash
docker compose --env-file .env -f infra/docker-compose.yml up -d --build zero-execution
```

**Or rebuild all services (if you want to be thorough):**

```bash
docker compose --env-file .env -f infra/docker-compose.yml up -d --build
```

---

### 3. Verify Execution Service Started

```bash
docker compose --env-file .env -f infra/docker-compose.yml logs zero-execution --tail=30
```

**Look for:**
- ✅ `Alpaca executor initialized (PAPER MODE)`
- ✅ `Database connected`
- ✅ `Redis connected`
- ✅ `Subscribed to chan:opportunity_update`
- ✅ `Health endpoint listening on port 8003`

**No errors about:**
- ❌ `MarketState` import errors
- ❌ `StandDownReason` not found
- ❌ Schema validation errors

---

### 4. Test TradeUpdate with MarketState Schema

**Publish a test opportunity:**

```bash
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

docker compose --env-file .env -f infra/docker-compose.yml exec redis redis-cli PUBLISH chan:opportunity_update "{
  \"schema_version\":\"1.0\",
  \"timestamp\":\"$NOW\",
  \"horizon\":\"H30\",
  \"rank_time\":\"$NOW\",
  \"total_candidates\":1,
  \"opportunities\":[
    {
      \"schema_version\":\"1.0\",
      \"timestamp\":\"$NOW\",
      \"ticker\":\"SPY\",
      \"horizon\":\"H30\",
      \"opportunity_score\":95,
      \"probability\":0.95,
      \"target_atr\":1.5,
      \"stop_atr\":0.75,
      \"market_state\":\"GREEN\",
      \"attention_stability_score\":80,
      \"attention_bucket\":\"STABLE\",
      \"attention_alignment\":80,
      \"why\":[\"TEST: Schema improvements\"],
      \"liquidity_grade\":\"A\"
    }
  ]
}"
```

**Check execution logs:**

```bash
docker compose --env-file .env -f infra/docker-compose.yml logs zero-execution --tail=20
```

**Verify DB insert (should have proper MarketState JSON):**

```bash
docker compose --env-file .env -f infra/docker-compose.yml exec timescaledb \
  psql -U zero_user -d zero_trading -c "SELECT execution_id, ticker, status, market_state_snapshot FROM execution_log ORDER BY time DESC LIMIT 1;"
```

**Expected:** `market_state_snapshot` should be valid JSON with `state`, `reason`, `vix_level`, etc.

---

### 5. Verify Health Endpoint

```bash
curl http://localhost:8003/health | python3 -m json.tool
```

**Or:**

```bash
docker compose --env-file .env -f infra/docker-compose.yml exec zero-execution \
  python3 -c "import urllib.request; import json; print(json.dumps(json.loads(urllib.request.urlopen('http://localhost:8003/health').read()), indent=2))"
```

**Expected:** JSON response with `paper_mode: true`, `execution_enabled: true/false`, `last_event` (if any).

---

## What Changed (Summary)

### Contract Fixes:
1. **SPEC_LOCK.md** - Clarified paper-only execution is opt-in (not a violation)
2. **StandDownSignal** - Renamed from `StandDownReason` to match Redis contract
3. **TradeUpdate.market_state** - Now uses `MarketState` schema (not `Dict[str, Any]`)
4. **BaseSchema.timestamp** - Now timezone-aware UTC (not naive `datetime.utcnow()`)
5. **db_schema.md** - Added `execution_log` table documentation

### Code Changes:
- **services/execution/main.py** - Updated to:
  - Convert market state dict to `MarketState` schema object
  - Use `TradeUpdate` Pydantic model for validation
  - Properly serialize `MarketState` in trade updates

---

## Troubleshooting

### If execution service fails to start:

**Check logs:**
```bash
docker compose --env-file .env -f infra/docker-compose.yml logs zero-execution
```

**Common issues:**
- **Import error:** Rebuild the image (step 2)
- **Schema validation error:** Check that `contracts/schemas.py` was pulled correctly
- **MarketState error:** Verify `MarketState` is imported in `main.py`

### If DB insert fails:

**Check the error:**
```bash
docker compose --env-file .env -f infra/docker-compose.yml logs zero-execution | grep -i "execution_log\|error"
```

**Verify table exists:**
```bash
docker compose --env-file .env -f infra/docker-compose.yml exec timescaledb \
  psql -U zero_user -d zero_trading -c "\d execution_log"
```

---

## Verification Checklist

- [ ] Git pull completed successfully
- [ ] Execution service rebuilt
- [ ] Execution service started without errors
- [ ] Health endpoint returns valid JSON
- [ ] Test opportunity creates DB row with valid `market_state_snapshot`
- [ ] No schema validation errors in logs

---

**Done!** Your system now has:
- ✅ Proper contract alignment
- ✅ Type-safe MarketState in TradeUpdate
- ✅ Timezone-aware timestamps
- ✅ Complete execution_log documentation
