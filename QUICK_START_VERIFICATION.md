# Quick Start: System Verification

## 🚀 Fast Track (5 Minutes)

### Step 1: Install Dependencies

```bash
pip install -r scripts/requirements.txt
```

### Step 2: Configure Alpaca Credentials

Edit your `.env` file (create from `.env.example` if needed):

```bash
# Add your Alpaca credentials (from ELVA or your Alpaca account)
ALPACA_API_KEY=your_key_here
ALPACA_SECRET_KEY=your_secret_here
ALPACA_PAPER=true

# Set provider to Alpaca
PROVIDER_TYPE=alpaca
```

### Step 3: Start Infrastructure

```bash
# From project root
make up
```

Wait ~30 seconds for all services to start.

### Step 4: Run Verification

```bash
python scripts/verify_system.py
```

## ✅ Expected Results

You should see:

```
✅ Infrastructure Ready
✅ Ingestion service: Running
✅ Alpaca API: Connected
✅ Data Persistence: Verified
✅ Redis Pub/Sub: Messages received
```

## 🔧 Troubleshooting

### "Redis Connection Failed"
```bash
# Check if Redis is running
docker compose -f infra/docker-compose.yml ps redis

# Restart if needed
docker compose -f infra/docker-compose.yml restart redis
```

### "TimescaleDB Connection Failed"
```bash
# Check if TimescaleDB is running
docker compose -f infra/docker-compose.yml ps timescaledb

# Check logs
docker compose -f infra/docker-compose.yml logs timescaledb

# Restart if needed
docker compose -f infra/docker-compose.yml restart timescaledb
```

### "Alpaca API Connection Failed"
- Verify your API keys in `.env`
- Check API key has market data permissions
- Ensure network connectivity

### "No Data Found"
- Market may be closed (weekend/holiday)
- Ingestion service may need to run longer
- Check ingestion logs: `docker compose -f infra/docker-compose.yml logs zero-ingest-price`

## 📊 Manual Verification

If automated script fails, verify manually:

### 1. Check Infrastructure
```bash
# Redis
docker compose -f infra/docker-compose.yml exec redis redis-cli ping
# Should return: PONG

# TimescaleDB
make psql
# In psql: SELECT COUNT(*) FROM candles_1m;
```

### 2. Check Ingestion Service
```bash
curl http://localhost:8080/health
```

### 3. Check Data
```bash
make psql
```

In psql:
```sql
-- Check recent candles
SELECT ticker, COUNT(*) as count, MAX(time) as latest
FROM candles_1m
WHERE time >= NOW() - INTERVAL '7 days'
GROUP BY ticker;

-- Check for gaps
SELECT COUNT(*) FROM ingest_gap_log WHERE backfilled = false;
```

## 🎯 Next Steps

Once verification passes:
1. ✅ Infrastructure is ready
2. ✅ Alpaca integration working
3. ✅ Data pipeline operational

You can now:
- Monitor ingestion: `docker compose -f infra/docker-compose.yml logs -f zero-ingest-price`
- View data in Grafana: `http://localhost:3000`
- Proceed to Milestone 2 (Regime Engine)

