# Immediate Fixes Needed

## Issue 1: Ingest Service - Redis Package Missing

**Error**: `ModuleNotFoundError: No module named 'redis.asyncio'`

**Cause**: The container was built but redis package didn't install, OR container is using cached/old layer.

**Fix on Jetson**:

```bash
# Stop services
make down

# Force remove the image
docker rmi infra-zero-ingest-price

# Rebuild ingest service (this will install redis>=5.0.0)
docker compose --env-file .env -f infra/docker-compose.yml build --no-cache zero-ingest-price

# Restart services
make up
```

**Verify redis is installed in container** (optional):
```bash
docker compose --env-file .env -f infra/docker-compose.yml run --rm zero-ingest-price pip list | grep redis
```

Should show: `redis 5.x.x`

---

## Issue 2: Regime Service - Table Doesn't Exist Error

**Error**: `relation "regime_log" does not exist`

**Cause**: The service started BEFORE `init-db` ran, so it saw an error on first connection. The table EXISTS now (we saw it created), but the service needs to reconnect.

**Fix on Jetson**:

```bash
# Just restart the regime service (table exists, service just needs to reconnect)
docker compose --env-file .env -f infra/docker-compose.yml restart zero-regime

# Verify table exists
docker compose --env-file .env -f infra/docker-compose.yml exec timescaledb psql -U zero_user -d zero_trading -c "\dt" | grep regime_log
```

The error in logs is from the FIRST attempt (before init-db ran). After restart, it should work fine.

---

## Complete Fix Script

Run this on Jetson:

```bash
# 1. Stop all
make down

# 2. Remove ingest image
docker rmi infra-zero-ingest-price

# 3. Rebuild ingest
docker compose --env-file .env -f infra/docker-compose.yml build --no-cache zero-ingest-price

# 4. Start services
make up

# 5. Wait 10 seconds, then restart regime (to clear the old error)
sleep 10
docker compose --env-file .env -f infra/docker-compose.yml restart zero-regime

# 6. Check status
make status
```

---

## Expected Results After Fix

- ✅ **zero-ingest-price**: Should start without redis errors
- ✅ **zero-regime**: Should work (table exists, just needed restart)
- ✅ **zero-scanner**: Already working fine
- ✅ All services: Healthy/running
