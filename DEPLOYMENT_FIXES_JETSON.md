# Deployment Fixes for Jetson

## Current Issues

1. **Ingest service**: Redis package not installed (old container cache)
2. **Database schema**: `regime_log` table missing (init.sql didn't run)
3. **Password warnings**: Not critical, but use `make` commands

## Quick Fix (Automated)

Run the fix script:

```bash
cd ~/zero-trading-intelligence
chmod +x scripts/fix_deployment.sh
./scripts/fix_deployment.sh
```

## Manual Fix (Step by Step)

### 1. Fix Ingest Service (Redis Package)

```bash
# Stop services
make down

# Rebuild ingest service without cache
docker compose --env-file .env -f infra/docker-compose.yml build --no-cache zero-ingest-price

# Or rebuild all services
docker compose --env-file .env -f infra/docker-compose.yml build --no-cache
```

### 2. Fix Database Schema (Missing Tables)

The `init.sql` script only runs when the database is first created. If the database already exists, you need to run it manually:

```bash
# Make sure TimescaleDB is running
docker compose --env-file .env -f infra/docker-compose.yml up -d timescaledb

# Wait for it to be ready
sleep 10

# Run init.sql manually
docker compose --env-file .env -f infra/docker-compose.yml exec -T timescaledb psql -U zero_user -d zero_trading -f /docker-entrypoint-initdb.d/init.sql
```

**Note**: If tables already exist, this will show errors like "already exists" - that's OK, the script is idempotent.

### 3. Start All Services

```bash
make up
```

Or manually:

```bash
docker compose --env-file .env -f infra/docker-compose.yml up -d
```

### 4. Verify Everything Works

```bash
# Check status
make status

# Check logs
docker compose --env-file .env -f infra/docker-compose.yml logs zero-ingest-price --tail=20
docker compose --env-file .env -f infra/docker-compose.yml logs zero-regime --tail=20
docker compose --env-file .env -f infra/docker-compose.yml logs zero-scanner --tail=20
```

## Expected Results

After fixes:
- ✅ `zero-ingest-price`: Should start without redis import errors
- ✅ `zero-regime`: Should connect to DB and log state changes (no "regime_log does not exist" error)
- ✅ `zero-scanner`: Already working, should continue working
- ✅ Password warnings: Will still appear if you run `docker compose` directly (use `make` commands instead)

## If Database Schema Already Exists

If you get errors like "relation already exists" when running init.sql, that's fine - the script is idempotent. The important thing is that all tables exist.

To check which tables exist:

```bash
docker compose --env-file .env -f infra/docker-compose.yml exec -T timescaledb psql -U zero_user -d zero_trading -c "\dt"
```

You should see:
- `candles_1m`
- `regime_log`
- `scanner_log`
- `opportunity_log`

## Troubleshooting

**If ingest still fails after rebuild:**
- Check the Dockerfile is using the correct requirements.txt
- Verify requirements.txt has `redis>=5.0.0`
- Try: `docker compose --env-file .env -f infra/docker-compose.yml build --no-cache --pull zero-ingest-price`

**If database schema still missing:**
- Check init.sql file exists: `ls -la infra/db/init.sql`
- Check database is accessible: `docker compose --env-file .env -f infra/docker-compose.yml exec timescaledb psql -U zero_user -d zero_trading -c "SELECT 1;"`
- Try running SQL commands manually from init.sql
