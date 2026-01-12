# How to Verify Everything is Working on Jetson

## ✅ Quick Health Check (30 seconds)

### 1. Check Service Status
```bash
make status
```

**Expected Output:**
- ✅ All services show `Up` status
- ✅ `zero-timescaledb`: `healthy`
- ✅ `zero-redis`: `healthy`
- ✅ `zero-regime`: `healthy`
- ✅ `zero-ingest-price`: `healthy` (or `starting` - wait 30s)
- ✅ `zero-scanner`: `healthy` (or `starting` - wait 30s)
- ⚠️ `zero-grafana`: Can be `restarting` (optional, not critical)

---

### 2. Check Service Logs (No Errors)
```bash
# Ingest service - should have NO redis import errors
docker compose --env-file .env -f infra/docker-compose.yml logs zero-ingest-price --tail=20

# Regime service - should show "Market state changed" messages, NO table errors
docker compose --env-file .env -f infra/docker-compose.yml logs zero-regime --tail=20

# Scanner service - should show "Connected" and "Subscribed" messages
docker compose --env-file .env -f infra/docker-compose.yml logs zero-scanner --tail=20
```

**What to Look For:**
- ✅ **Ingest**: No `ModuleNotFoundError`, should show ingestion messages
- ✅ **Regime**: No `relation does not exist` errors, should show state changes
- ✅ **Scanner**: Connected to DB/Redis, subscribed to channels

---

## 🔍 Detailed Verification (2-3 minutes)

### 3. Test Health Endpoints

```bash
# Regime service health (port 8000)
curl http://localhost:8000/health

# Scanner service health (port 8001)
curl http://localhost:8001/health

# Ingest service health (port 8080)
curl http://localhost:8080/health
```

**Expected Response:** JSON with `status: "healthy"` or `status: "ok"`

---

### 4. Check Database Tables Exist

```bash
make psql
# Then inside psql:
\dt
# You should see: candles_1m, regime_log, scanner_log, opportunity_log, etc.
\q
```

**Expected Tables:**
- `candles_1m`, `candles_5m`, `candles_1d`
- `regime_log`
- `scanner_log`, `opportunity_log`
- `ingest_gap_log`

---

### 5. Check Redis Keys/State

```bash
make redis-cli
# Then inside redis-cli:
KEYS *
# You should see keys like: market_state, scanner_state, etc.
GET market_state
# Should return JSON with state (GREEN/YELLOW/RED)
exit
```

**Expected Keys:**
- `market_state` - Current market regime state
- `scanner_state` or `active_candidates` - Scanner results

---

## 🧪 Automated Verification Script

Use the built-in verification script:

```bash
# Run full system verification
python scripts/verify_state.py
```

**Expected Output:**
- Report card showing PASS/WARN/FAIL for each milestone
- Exit code 0 if all pass (or warnings only)
- Exit code 1 if any critical failures

---

## 📊 What "Working" Looks Like

### ✅ All Systems Operational Means:

1. **Infrastructure:**
   - TimescaleDB: Healthy, all tables exist
   - Redis: Healthy, keys being updated
   - Services: All core services (ingest/regime/scanner) are healthy

2. **Ingest Service (Milestone 1):**
   - Running without errors
   - Writing candles to database
   - Publishing events to Redis
   - Health endpoint responds

3. **Regime Service (Milestone 2):**
   - Running without errors
   - Calculating market state (GREEN/YELLOW/RED)
   - Publishing state to Redis (`key:market_state`)
   - Logging state changes to `regime_log` table
   - Health endpoint responds

4. **Scanner Service (Milestone 3):**
   - Running without errors
   - Respecting market state veto (sleeps when RED)
   - Scanning and finding candidates
   - Publishing to Redis (`key:scanner_state` or `key:active_candidates`)
   - Logging to `scanner_log` table
   - Health endpoint responds

---

## 🚨 Common Issues to Watch For

### Issue: Services in "starting" state for > 2 minutes
**Action**: Check logs for errors

### Issue: Redis import errors in ingest
**Action**: Rebuild ingest container (see FIXES_NEEDED.md)

### Issue: "Table does not exist" errors
**Action**: Run `make init-db` to initialize schema

### Issue: Services restarting constantly
**Action**: Check logs, likely configuration or dependency issue

---

## 📝 Daily Health Check Checklist

Quick checklist to run daily:

```bash
# 1. Status check (10 seconds)
make status

# 2. Log check - any errors? (30 seconds)
docker compose --env-file .env -f infra/docker-compose.yml logs --tail=50 | grep -i error

# 3. Health endpoints (10 seconds)
curl -s http://localhost:8000/health | grep -q "healthy" && echo "✅ Regime OK" || echo "❌ Regime DOWN"
curl -s http://localhost:8001/health | grep -q "healthy" && echo "✅ Scanner OK" || echo "❌ Scanner DOWN"
curl -s http://localhost:8080/health | grep -q "ok\|healthy" && echo "✅ Ingest OK" || echo "❌ Ingest DOWN"

# 4. Database has data? (20 seconds)
docker compose --env-file .env -f infra/docker-compose.yml exec -T timescaledb psql -U zero_user -d zero_trading -c "SELECT COUNT(*) FROM candles_1m;" | grep -E "[0-9]+" && echo "✅ Database has data"

# 5. Redis has state? (10 seconds)
docker compose --env-file .env -f infra/docker-compose.yml exec redis redis-cli GET market_state | grep -q "state" && echo "✅ Redis has state" || echo "⚠️  Redis state missing"
```

**All green?** ✅ System is healthy!

---

## 🎯 What Success Looks Like

When everything is working:

1. ✅ `make status` shows all services `healthy`
2. ✅ No errors in logs (only INFO/WARNING messages)
3. ✅ Health endpoints return 200 OK
4. ✅ Database has tables and data (candles, regime_log entries)
5. ✅ Redis has state keys (`market_state`, scanner state)
6. ✅ Services are processing data (logs show activity)
7. ✅ `verify_state.py` script passes

**If all above are true, your system is fully operational!** 🎉

---

## 📞 Next Steps After Verification

Once everything is verified working:

1. **Monitor logs** periodically: `make logs` (Ctrl+C to exit)
2. **Check data accumulation**: Verify candles are being written
3. **Verify regime logic**: Check that market state changes appropriately
4. **Verify scanner**: Check that candidates are being found (when market is GREEN)
5. **Optional**: Fix Grafana if you want visual dashboards

---

## 🔧 Troubleshooting Quick Reference

| Symptom | Quick Check | Solution |
|---------|-------------|----------|
| Service won't start | `make status` | Check logs for errors |
| Redis errors | `docker compose logs zero-ingest-price` | Rebuild ingest container |
| Table errors | `make psql` then `\dt` | Run `make init-db` |
| Services restarting | `make status` | Check dependencies, logs |
| No data in DB | `SELECT COUNT(*) FROM candles_1m;` | Check ingest service logs |

---

**Remember**: Grafana is optional - core services work without it!
