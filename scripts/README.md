# ZERO Verification Scripts

## verify_system.py

Comprehensive system verification script for Milestone 0 + Milestone 1.

### Prerequisites

```bash
pip install -r scripts/requirements.txt
```

### Setup

1. **Copy `.env.example` to `.env`** (if not already done)
2. **Add your Alpaca credentials** to `.env`:
   ```bash
   ALPACA_API_KEY=your_key_here
   ALPACA_SECRET_KEY=your_secret_here
   ALPACA_PAPER=true
   ```

### Usage

**From project root:**
```bash
python scripts/verify_system.py
```

**Or make it executable:**
```bash
chmod +x scripts/verify_system.py
./scripts/verify_system.py
```

### What It Checks

1. **Infrastructure**
   - Redis connectivity (PING)
   - TimescaleDB connectivity
   - Required tables exist (candles_1m, candles_5m, candles_1d, ticks, ingest_gap_log)
   - Hypertables configured

2. **Ingestion Service**
   - Health endpoint reachable
   - Service status

3. **Alpaca API**
   - Connection test
   - Data retrieval test (last 10 days for SPY)

4. **Data Persistence**
   - Row counts in candles_1m, candles_5m
   - Latest candle timestamps
   - Gap log status

5. **Redis Pub/Sub**
   - Subscribes to `chan:ticker_update`
   - Verifies messages are being published

### Expected Output

```
============================================================
ZERO SYSTEM VERIFICATION
============================================================
Time: 2026-01-11T12:00:00

============================================================
STEP 1: Infrastructure Check
============================================================
Checking Redis...
✅ Redis: Connected
Checking TimescaleDB...
✅ TimescaleDB: Connected (found 5 required tables)
✅ TimescaleDB: 5 hypertables configured

✅ Infrastructure Ready

[... more steps ...]

============================================================
VERIFICATION SUMMARY
============================================================
INFRASTRUCTURE      ✅ PASS
INGESTION           ✅ PASS
ALPACA              ✅ PASS
PERSISTENCE         ✅ PASS
REDIS_EVENTS        ✅ PASS

✅ SYSTEM VERIFIED: Infrastructure and data persistence working
```

### Troubleshooting

**Redis Connection Failed:**
- Ensure Redis container is running: `make up`
- Check `REDIS_HOST` and `REDIS_PORT` in `.env`

**TimescaleDB Connection Failed:**
- Ensure TimescaleDB container is running: `make up`
- Check `DB_*` variables in `.env`
- Verify `init.sql` ran successfully

**Alpaca API Failed:**
- Verify `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` in `.env`
- Check API key permissions (market data access)
- Ensure network connectivity

**No Data Found:**
- Market may be closed (weekend/holiday)
- Ingestion service may not have run yet
- Set `PROVIDER_TYPE=alpaca` in `.env` and restart service

