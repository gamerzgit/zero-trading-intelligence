# ZERO Core Logic Service (Milestone 4)

**Level 3: Opportunity Ranking**

## Purpose

The `zero-core-logic` service takes "Active Candidates" from the Scanner and **RANKS** them using deterministic, explainable scoring.

It answers: *"Which opportunities have the highest quality score and confidence?"*

**NOTE:** This service outputs **confidence** (heuristic), not real-world probability. True probability calibration happens in Milestone 6 (Truth Test).

## Key Features

- ✅ **Deterministic Scoring:** Calculates opportunity scores (0-100) with explainable components
- ✅ **Confidence Bands:** Converts scores to confidence bands (LOW/MED/HIGH) and confidence_pct (heuristic)
- ✅ **Multi-Timeframe Features:** Uses 1m, 5m, and optionally 1d candles for robust analysis
- ✅ **Multi-Factor Analysis:** Momentum, Volatility, Liquidity, Stability
- ✅ **MarketState Penalties:** Applies penalties (not bonuses) for YELLOW state
- ✅ **Veto Aware:** If MarketState is RED, does not rank/publish
- ✅ **Top-N Ranking:** Ranks and publishes Top 10 opportunities
- ✅ **Database Logging:** Writes Top 5 opportunities to `opportunity_log` table

## Architecture

### Inputs

1. **Subscribes to `chan:active_candidates`** (from Scanner)
   - Receives `CandidateList` messages per horizon
   - Triggers ranking process

2. **Reads `key:market_state`** (from Regime Engine)
   - Context for MarketState adjustments (penalties)
   - Veto check (RED = no ranking)

3. **Reads `candles_1m`, `candles_5m`, and optionally `candles_1d` from TimescaleDB**
   - 1m: For immediacy and short-term momentum
   - 5m: For stability and structure confirmation
   - 1d: For swing horizon alignment (HDAY, HWEEK)

### Scoring Logic

1. **Momentum Score (0-100):**
   - EMA Alignment: Price > EMA9 > EMA20 (1m + 5m)
   - EMA slope (rate of change)
   - Weight: 40% of total score

2. **Volatility Score (0-100):**
   - ATR level (5m timeframe)
   - ATR expansion (increasing volatility)
   - Weight: 25% of total score

3. **Liquidity Score (0-100):**
   - Relative volume (1m + 5m)
   - Activity level assessment
   - Weight: 20% of total score

4. **Stability Score (0-100):**
   - Divergence between 1m and 5m trends
   - Lower divergence = higher stability
   - Weight: 15% of total score

**Base Score:** Weighted average of all components

### MarketState Adjustment (Penalties, NOT Bonuses)

- **GREEN:** No penalty (base score unchanged)
- **YELLOW:** Apply penalty (-10 score cap or confidence reduction)
- **RED:** Skip ranking entirely (veto)

### Confidence Conversion (HEURISTIC)

- **Confidence Band:**
  - Score 0-40: LOW confidence
  - Score 40-70: MED confidence
  - Score 70-100: HIGH confidence

- **Confidence Percentage (0.0-0.95):**
  - Score 0-50: Linear mapping → 0.0-0.50
  - Score 50-100: Exponential curve → 0.50-0.95
  - YELLOW state: Additional 15% reduction
  - Max: 0.95 (nothing is certain)

**NOTE:** This is HEURISTIC until Milestone 6 (Truth Test calibration). The `probability` field in the schema is mapped from `confidence_pct` for contract compliance.

### Outputs

1. **Redis:**
   - Publishes to `chan:opportunity_update` (Pub/Sub)
   - Stores in `key:opportunity_rank` (TTL: 60s)
   - Payload: `OpportunityRank` schema (Top 10)

2. **Database:**
   - Writes to `opportunity_log` table
   - **Only Top 5** opportunities are logged
   - Full Level 3 schema with all fields

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

# API
CORE_API_PORT=8002
```

## Usage

### Docker Compose

```bash
# Start core logic service
docker compose --env-file .env -f infra/docker-compose.yml up zero-core-logic

# View logs
docker compose --env-file .env -f infra/docker-compose.yml logs -f zero-core-logic

# Check health
curl http://localhost:8002/health
```

### Health Endpoint

```bash
GET /health
```

Response:
```json
{
  "service": "zero-core-logic",
  "status": "healthy",
  "last_update": "2026-01-11T20:00:00Z",
  "details": {
    "is_running": true,
    "last_ranking_time": "2026-01-11T19:59:00Z",
    "current_rankings": {
      "H30": 5,
      "H2H": 8,
      "HDAY": 12,
      "HWEEK": 15
    },
    "db_connected": true,
    "redis_connected": true,
    "market_state": "GREEN"
  }
}
```

## Behavior

### MarketState Veto

- **RED:** Service does not rank/publish (logs veto message)
- **YELLOW:** Service ranks normally (with reduced confluence bonus)
- **GREEN:** Service ranks normally (with maximum confluence bonus)

### Ranking Process

1. Receive `CandidateList` from Scanner
2. Load current `MarketState` from Redis
3. For each candidate:
   - Fetch recent candles from DB
   - Calculate momentum score (EMA alignment)
   - Calculate volatility score (ATR expansion)
   - Calculate confluence bonus (market state)
   - Convert total score to probability
   - Create `Opportunity` object
4. Sort by `opportunity_score` (descending)
5. Take Top 10 for Redis
6. Take Top 5 for database

### Target/Stop ATR Multiples

Different horizons use different ATR multiples:

- **H30 (30-min):** 1.5 ATR target, 0.75 ATR stop
- **H2H (2-hour):** 2.0 ATR target, 1.0 ATR stop
- **HDAY (daily):** 3.0 ATR target, 1.5 ATR stop
- **HWEEK (weekly):** 5.0 ATR target, 2.5 ATR stop

## Dependencies

- `asyncpg`: PostgreSQL/TimescaleDB async driver
- `redis`: Redis async client
- `aiohttp`: HTTP server for health endpoint
- `pandas`: Data analysis (EMA, ATR calculations)
- `numpy`: Numerical operations
- `pydantic`: Data validation

## Future Enhancements

- [ ] Load `attention_stability_score` from `key:attention_state` (currently defaults to 50)
- [ ] Add regime dependency logic
- [ ] Add VWAP/support/resistance key levels
- [ ] Add invalidation rules
- [ ] Add liquidity grade assessment
- [ ] Optimize database queries (batch fetching)
- [ ] Add caching for frequently accessed candles

## Notes

- **Top 10 for Redis, Top 5 for DB:** This is by design to reduce database write load
- **Max Probability 95%:** Nothing is certain in trading
- **Veto on RED:** Service respects market permission state
- **Event-Driven:** Only ranks when Scanner publishes new candidates
