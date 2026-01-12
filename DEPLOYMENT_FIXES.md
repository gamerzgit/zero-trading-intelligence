# Deployment Fixes Applied

## Issues Fixed

### 1. Regime Service - Missing aiohttp Dependency
**Problem:** `ModuleNotFoundError: No module named 'aiohttp'`

**Fix:** Added `aiohttp>=3.9.0` to `services/regime/requirements.txt`

### 2. Ingest Service - Python Import Error
**Problem:** `ImportError: attempted relative import beyond top-level package`

**Fix:** Changed relative imports to absolute imports in:
- `services/ingest/db/writer.py`: Changed `from ..provider.base import Candle` to `from provider.base import Candle`
- `services/ingest/redis/publisher.py`: Changed `from ..provider.base import Candle` to `from provider.base import Candle`

The Dockerfile sets `PYTHONPATH=/app` and copies `services/ingest/` to `/app/`, so absolute imports work correctly.

### 3. DB Password Issue
**Problem:** Docker Compose warnings about `DB_PASSWORD` and `POSTGRES_PASSWORD` not being set

**Status:** This is a warning but TimescaleDB started successfully. The containers will need to be rebuilt anyway after the dependency fixes.

## Next Steps

**On your Jetson, rebuild the containers:**

```bash
# Rebuild all services (this will install the new dependencies)
docker compose -f infra/docker-compose.yml build

# Restart services
make down
make up
```

**Or rebuild specific services:**
```bash
# Rebuild just the services that had issues
docker compose -f infra/docker-compose.yml build zero-regime zero-ingest-price

# Restart
make down
make up
```

## Files Changed

- `services/regime/requirements.txt` - Added aiohttp
- `services/ingest/db/writer.py` - Fixed import
- `services/ingest/redis/publisher.py` - Fixed import
