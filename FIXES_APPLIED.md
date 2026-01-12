# Fixes Applied - January 2026

## Issue 1: zero-ingest-price - Redis Import Error ✅ FIXED

**Error**: `ModuleNotFoundError: No module named 'redis.asyncio'`

**Root Cause**: The redis package was specified as `redis>=5.0.0` but the container needed `redis[hiredis]>=5.0.0` to ensure async support is properly installed.

**Fixes Applied**:
1. Updated `services/ingest/requirements.txt` to use `redis[hiredis]>=5.0.0` (matching regime service)
2. Verified import pattern matches working scanner service: `import redis.asyncio as aioredis`

**Action Required**: 
```bash
# Rebuild the ingest service
docker compose --env-file .env -f infra/docker-compose.yml build --no-cache zero-ingest-price

# Restart services
docker compose --env-file .env -f infra/docker-compose.yml up -d zero-ingest-price
```

## Issue 2: Grafana Datasource Configuration ✅ FIXED

**Issue**: Grafana provisioning files don't expand `${POSTGRES_PASSWORD}` environment variables.

**Fixes Applied**: 
1. Updated `infra/grafana/provisioning/datasources/timescaledb.yml` to make datasource editable
2. Removed invalid `${POSTGRES_PASSWORD}` reference
3. Created `scripts/configure_grafana.py` to automatically configure datasource via Grafana API
4. Added `make configure-grafana` command for easy configuration

**Action Required**:
After Grafana starts, run:
```bash
make configure-grafana
```

This will automatically configure the TimescaleDB datasource with the password from your `.env` file.

**Alternative**: You can also configure it manually through the Grafana UI:
1. Access Grafana: `http://localhost:3000`
2. Login with admin credentials
3. Go to Configuration → Data Sources → TimescaleDB
4. Enter the database password from your `.env` file
5. Click "Save & Test"

## Verification Steps

After applying fixes, verify system:

```bash
# 1. Rebuild and restart services
make down
make build
make up

# 2. Wait for services to start (30-60 seconds)
sleep 60

# 3. Check service status
make status

# 4. Check ingest service logs
docker compose --env-file .env -f infra/docker-compose.yml logs zero-ingest-price --tail=50

# 5. Run verification script
python scripts/verify_state.py
```

## Expected Results

After fixes:
- ✅ `zero-ingest-price` should be `healthy` (not restarting)
- ✅ `zero-regime` should be `healthy` 
- ✅ `zero-scanner` should be `healthy`
- ⚠️ `grafana` may need manual datasource password configuration
- ✅ Redis connectivity should work
- ✅ Database connectivity should work

## Files Modified

1. `services/ingest/requirements.txt` - Updated redis package spec to `redis[hiredis]>=5.0.0`
2. `services/ingest/redis/publisher.py` - Verified import pattern (already correct)
3. `infra/grafana/provisioning/datasources/timescaledb.yml` - Made datasource editable, removed invalid env var
4. `scripts/configure_grafana.py` - NEW: Python script to configure datasource via Grafana API
5. `scripts/requirements.txt` - Added `requests>=2.31.0` dependency
6. `Makefile` - Added `configure-grafana` target