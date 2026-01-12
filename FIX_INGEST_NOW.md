# URGENT: Fix Ingest Service - Redis Package Missing

## The Problem
Your ingest service container is still using an OLD image that doesn't have the redis package installed. You need to FORCE remove the old image and rebuild.

## The Fix (Run This Now)

```bash
# 1. Stop all services
make down

# 2. FORCE remove the old ingest image (important - this removes it even if containers are using it)
docker rmi -f infra-zero-ingest-price

# 3. Verify it's gone (optional)
docker images | grep zero-ingest-price
# Should show nothing, or an error

# 4. Rebuild ingest service with NO cache
docker compose --env-file .env -f infra/docker-compose.yml build --no-cache zero-ingest-price

# 5. Start services
make up

# 6. Check logs - should see NO redis errors
docker compose --env-file .env -f infra/docker-compose.yml logs zero-ingest-price --tail=30
```

## What You Should See After Fix

**In logs, you should see:**
- ✅ NO `ModuleNotFoundError: No module named 'redis.asyncio'` errors
- ✅ Service starting messages
- ✅ Connections to Redis and Database

**NOT:**
- ❌ Redis import errors
- ❌ ModuleNotFoundError

## Verify It Worked

```bash
# Check if redis is installed in the container
docker compose --env-file .env -f infra/docker-compose.yml run --rm zero-ingest-price pip list | grep redis

# Should show: redis 5.x.x (some version 5.x)
```

## After Fix, Run Verification Again

```bash
python scripts/verify_state.py
```

Most failures should clear once ingest is fixed.
