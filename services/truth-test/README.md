# ZERO Truth Test Service (Milestone 7)

## Purpose

Evaluates opportunity outcomes after market close and computes calibration factors for probability adjustment.

Per SPEC_LOCK §6: Truth Test Requirements
- Evaluate every opportunity emitted
- Compute realized MFE/MAE over exact horizon window
- Store results for calibration
- Publish calibration state to Redis

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ZERO Truth Test Service                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │   Scheduler  │───▶│   Evaluator  │───▶│  Calibration │   │
│  │  (4pm ET)    │    │  (MFE/MAE)   │    │   Engine     │   │
│  └──────────────┘    └──────────────┘    └──────────────┘   │
│         │                   │                   │            │
│         ▼                   ▼                   ▼            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                    Database Layer                     │   │
│  │  - Read: opportunity_log, candles_1m/5m              │   │
│  │  - Write: performance_log                            │   │
│  └──────────────────────────────────────────────────────┘   │
│                            │                                 │
│                            ▼                                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                    Redis                              │   │
│  │  - Publish: key:calibration_state                    │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Evaluation Logic

### LONG-Only Assumption (MVP)

For each opportunity:

1. **Entry Reference Price**: 1m candle close at (or within +2 min of) issue time
2. **Target/Stop Prices**:
   - `target_price = entry_price + (target_atr × ATR)`
   - `stop_price = entry_price - (stop_atr × ATR)`
3. **Walk Forward**: Candle-by-candle until horizon end
4. **Track**:
   - MFE = max(high - entry_price) — favorable move UP
   - MAE = max(entry_price - low) — adverse move DOWN
5. **Outcome**:
   - PASS: Target hit before stop
   - FAIL: Stop hit before target
   - EXPIRED: Neither hit within horizon
   - NO_DATA: Missing candles or ATR

## Calibration

### Shrink Factors

Based on historical pass rates per bucket (horizon × market_state × attention_bucket):

| Pass Rate | Shrink Factor |
|-----------|---------------|
| < 35%     | 0.50          |
| 35-45%    | 0.70          |
| 45-50%    | 0.85          |
| 50-55%    | 0.95          |
| > 55%     | 1.00          |

**Key Rule**: Never boost above 1.0 (only shrink)

### Redis Output

```json
{
  "timestamp": "2026-01-15T21:05:00Z",
  "version": "1.0",
  "buckets": {
    "H30_GREEN_STABLE": {
      "horizon": "H30",
      "regime_state": "GREEN",
      "attention_bucket": "STABLE",
      "total_signals": 150,
      "pass_count": 85,
      "fail_count": 65,
      "pass_rate": 0.5667,
      "shrink_factor": 1.00
    }
  },
  "global_stats": {
    "total_signals": 500,
    "global_pass_rate": 0.52,
    "global_shrink": 0.95
  }
}
```

## API Endpoints

### Health Check
```
GET /health
```

### Manual Trigger
```
POST /run?date=YYYY-MM-DD
```

If `date` is provided, runs backfill for that date. Otherwise evaluates recent opportunities.

## Schedule

- Runs daily at **4:05pm ET** (5 minutes after market close)
- Skips weekends
- Can be manually triggered for backfills

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| DB_HOST | timescaledb | Database host |
| DB_PORT | 5432 | Database port |
| DB_NAME | zero_trading | Database name |
| DB_USER | zero_user | Database user |
| DB_PASSWORD | - | Database password |
| REDIS_HOST | redis | Redis host |
| REDIS_PORT | 6379 | Redis port |
| TRUTH_TEST_API_PORT | 8004 | HTTP API port |

## Database Tables

### Reads From
- `opportunity_log`: Opportunities to evaluate
- `candles_1m`: Price data for evaluation
- `candles_5m`: Fallback price data

### Writes To
- `performance_log`: Evaluation results

## Integration with Core

The `zero-core-logic` service reads `key:calibration_state` and applies shrink factors:

```python
probability_adj = clamp(probability_raw * shrink_factor, 0.0, 1.0)
```

This enforces SPEC_LOCK §6.2 Confidence Degradation.
