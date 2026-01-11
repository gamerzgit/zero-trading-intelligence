# ZERO Price Ingestion Service

**Milestone 1:** Pure ingestion + persistence service

## Overview

The `zero-ingest-price` service is responsible for:
- Ingesting market price data from providers
- Writing candles to TimescaleDB (1m, 5m, 1d)
- Publishing events to Redis Pub/Sub
- Detecting and logging data gaps

**It does NOT:**
- Perform scanning
- Perform ranking
- Perform regime logic
- Execute trades

## Configuration

Set in `.env`:

```bash
PROVIDER_TYPE=mock  # or "polygon"
POLYGON_API_KEY=    # Required if using polygon provider
```

## Symbols

Default symbols (MVP):
- SPY
- QQQ
- IWM
- AAPL
- MSFT

## Health Endpoint

```bash
curl http://localhost:8080/health
```

Returns:
- Service status
- Provider connectivity
- Database connectivity
- Redis connectivity
- Last candle times per symbol
- Candle counts per symbol

## Database Behavior

- Writes to `candles_1m` table
- Auto-aggregates to `candles_5m` (every 5 minutes)
- Auto-aggregates to `candles_1d` (at start of new day)
- Detects gaps and logs to `ingest_gap_log`

## Redis Events

Publishes to:
- `chan:ticker_update` - All tickers
- `chan:index_update` - SPY/QQQ/IWM only
- `chan:volatility_update` - Placeholder (future)

## Provider Abstraction

Supports multiple providers via `MarketDataProvider` interface:

- **MockProvider** - Generates fake data (default, for testing)
- **PolygonProvider** - Polygon.io REST API

To add new provider:
1. Implement `MarketDataProvider` interface
2. Add to `provider/__init__.py`
3. Update `main.py` to instantiate

## Notes on Ticks Table

If implementing tick/second-level data in the future:
- **MUST** handle `ingest_seq` column to ensure unique Primary Keys `(ticker, time, ingest_seq)`
- Required for high-frequency data to prevent collisions when multiple ticks share the same timestamp
- The `ingest_seq` is auto-incrementing (BIGSERIAL) and must be included in the INSERT statement
- Example: `INSERT INTO ticks (ticker, time, price, volume, ingest_seq, ...) VALUES (...)`

