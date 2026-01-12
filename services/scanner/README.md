# ZERO Scanner Service (Milestone 3)

**Level 2: Opportunity Discovery**

## Purpose

The `zero-scanner` service filters the universe (500+ tickers) down to a list of **"Active Candidates"** based on objective criteria.

It answers: *"What is liquid and moving right now?"*

## Key Features

- ✅ **Veto Aware:** Checks `MarketState` from Redis - if RED, scanner sleeps
- ✅ **Multi-Horizon:** Scans for INTRADAY (H30, H2H) and SWING (HDAY, HWEEK) candidates
- ✅ **Objective Filters:** Liquidity, Volatility, Structure (pattern placeholder)
- ✅ **No Ranking:** Only outputs qualifying symbols (ranking is Milestone 4)

## Architecture

### Inputs
- Subscribes to `chan:ticker_update` (live data) - *Future: real-time subscription*
- Reads `candles_1m` / `candles_5m` from TimescaleDB for history
- Reads `key:market_state` from Redis for veto check

### Filters

1. **Liquidity Filter:**
   - Minimum average daily volume: 100,000
   - Relative volume: >= 1.5x average
   - Filters out low-activity stocks

2. **Volatility Filter:**
   - ATR must be >= 1% of price
   - Price bounds: $5 - $10,000
   - Filters out "dead money"

3. **Structure Filter:**
   - Basic trend detection (SMA 9/21)
   - Placeholder for pattern recognition (Bull Flag, Hammer, etc.)
   - Filters out choppy/no-structure stocks

### Outputs

1. **Redis:**
   - Publishes to `chan:active_candidates` (Pub/Sub)
   - Stores in `key:active_candidates` (TTL: 300s)
   - Updates `key:last_scan_time`

2. **Database:**
   - Logs to `opportunity_log` (Level 2 - minimal data, no scores/probabilities)

## Configuration

### Environment Variables

```bash
# Database
DB_HOST=timescaledb
DB_PORT=5432
DB_NAME=zero_trading
DB_USER=zero_user
DB_PASSWORD=your_password

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Scanner
SCAN_INTERVAL_SECONDS=60  # Scan every 60 seconds

# API
API_PORT=8001
```

### Scan Universe

Default universe includes:
- Major indices (SPY, QQQ, IWM, DIA)
- Tech stocks (AAPL, MSFT, GOOGL, etc.)
- Finance, Healthcare, Consumer, Energy sectors

**Future:** Load from Redis `key:scan_universe` or config file

## Usage

### Docker Compose

```bash
# Start scanner service
docker compose -f infra/docker-compose.yml up zero-scanner

# View logs
docker compose -f infra/docker-compose.yml logs -f zero-scanner

# Check health
curl http://localhost:8001/health
```

### Health Endpoint

```bash
GET /health
```

Response:
```json
{
  "service": "zero-scanner",
  "status": "healthy",
  "last_update": "2026-01-11T20:00:00Z",
  "details": {
    "is_running": true,
    "last_scan_time": "2026-01-11T19:59:00Z",
    "current_candidates": {
      "H30": 5,
      "H2H": 8,
      "HDAY": 12,
      "HWEEK": 15
    },
    "scan_universe_size": 50,
    "db_connected": true,
    "redis_connected": true
  }
}
```

## Behavior

### MarketState Veto

- **RED:** Scanner sleeps (no scanning)
- **YELLOW:** Scanner runs (cautious mode)
- **GREEN:** Scanner runs (full mode)

### Scan Frequency

- Default: Every 60 seconds
- Configurable via `SCAN_INTERVAL_SECONDS`

### Candidate Output

Each horizon produces a separate candidate list:
- `H30`: 30-minute intraday candidates
- `H2H`: 2-hour intraday candidates
- `HDAY`: Daily swing candidates
- `HWEEK`: Weekly swing candidates

## Future Enhancements

- [ ] Real-time subscription to `chan:ticker_update` (currently polls DB)
- [ ] Pattern recognition (Bull Flag, Hammer, etc.)
- [ ] Configurable scan universe from Redis/config
- [ ] Filter statistics in `CandidateList.filter_stats`
- [ ] Sector/industry filtering
- [ ] Spread/liquidity grade filtering

## Dependencies

- `asyncpg`: PostgreSQL/TimescaleDB async driver
- `redis`: Redis async client
- `aiohttp`: HTTP server for health endpoint
- `pandas`: Data analysis
- `numpy`: Numerical operations
- `pydantic`: Data validation

## Notes

- **No Ranking:** This service only filters. Ranking/scoring happens in Milestone 4.
- **Minimal DB Logging:** Level 2 candidates logged with placeholder values for Level 3 fields.
- **ZERO-Native:** Uses ZERO terminology (Prime Window, etc.) - no external branding.

