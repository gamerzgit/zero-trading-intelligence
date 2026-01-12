# Fix for init-db Command

## Issue
The `make init-db` command was failing with:
```
psql:/docker-entrypoint-initdb.d/init.sql: error: could not read from input file: Is a directory
```

## Root Cause
The `exec -T` flag with direct `-f` file path wasn't working correctly. We need to use shell redirection or wrap in `sh -c`.

## Fix Applied
Changed from:
```makefile
docker compose exec -T timescaledb psql -U zero_user -d zero_trading -f /docker-entrypoint-initdb.d/init.sql
```

To:
```makefile
docker compose exec timescaledb sh -c 'psql -U zero_user -d zero_trading -f /docker-entrypoint-initdb.d/init.sql'
```

## Alternative: Manual Database Initialization

If `make init-db` still doesn't work, you can manually initialize:

```bash
# Option 1: Copy file into container and run
docker compose --env-file .env -f infra/docker-compose.yml exec timescaledb bash
# Inside container:
psql -U zero_user -d zero_trading -f /docker-entrypoint-initdb.d/init.sql
exit

# Option 2: Pipe SQL from host
cat infra/db/init.sql | docker compose --env-file .env -f infra/docker-compose.yml exec -T timescaledb psql -U zero_user -d zero_trading

# Option 3: Use docker compose run (creates new container)
docker compose --env-file .env -f infra/docker-compose.yml run --rm \
  -v $(pwd)/infra/db/init.sql:/init.sql:ro \
  timescaledb psql -U zero_user -d zero_trading -f /init.sql
```

## Verification

Check if tables exist:
```bash
docker compose --env-file .env -f infra/docker-compose.yml exec timescaledb psql -U zero_user -d zero_trading -c "\dt"
```

You should see:
- candles_1m
- regime_log
- scanner_log
- opportunity_log
- ingest_gap_log
