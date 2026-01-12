# Quick Fix for Current Issues

## Issue 1: Ingest Service - Redis Import Error

**Problem**: Container is using old code/image even after rebuild.

**Solution**: Stop containers, remove old images, rebuild fresh:

```bash
# Stop all services
make down

# Remove the old image
docker rmi infra-zero-ingest-price

# Rebuild with no cache
docker compose --env-file .env -f infra/docker-compose.yml build --no-cache zero-ingest-price

# Start services
make up
```

## Issue 2: Regime Service - Table Doesn't Exist

**Problem**: Service says `regime_log` doesn't exist, but we just created it.

**Check if table actually exists**:
```bash
docker compose --env-file .env -f infra/docker-compose.yml exec timescaledb psql -U zero_user -d zero_trading -c "\dt"
```

If the table exists, the service might need to reconnect. Restart the regime service:
```bash
docker compose --env-file .env -f infra/docker-compose.yml restart zero-regime
```

If the table doesn't exist, run init-db again:
```bash
make init-db
```

## Complete Fresh Start (If Issues Persist)

```bash
# Stop everything
make down

# Remove all service images
docker rmi infra-zero-ingest-price infra-zero-regime infra-zero-scanner

# Rebuild all
docker compose --env-file .env -f infra/docker-compose.yml build --no-cache

# Start services
make up
```
