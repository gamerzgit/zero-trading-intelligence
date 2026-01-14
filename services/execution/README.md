# ZERO Execution Gateway Service (Milestone 6)

**Paper-Only Execution Service with Kill Switch Protection**

## Overview

The execution gateway listens for opportunities from the core logic service and (only if explicitly enabled) places **PAPER** orders on Alpaca.

## Safety Features

### 1. Paper-Only Hard Enforcement
- Service **refuses to start** if `ALPACA_PAPER != true`
- Hard-coded `paper=True` in Alpaca client initialization

### 2. Kill Switch (Default OFF)
- Execution disabled unless Redis `key:execution_enabled == "true"`
- Service runs but logs "Execution disabled" if kill switch is off

### 3. Final Veto
- Checks `key:market_state` before every order
- Only trades if `MarketState.state == "GREEN"`
- Blocks with status "BLOCKED" if market is RED/YELLOW

### 4. Strict Thresholds
- Only considers opportunities with:
  - `probability >= 0.90`
  - `rank == 1` (top opportunity)

### 5. Hard Limits
- Quantity: **1 share max**
- Max 1 open position per ticker
- Cooldown: 60 minutes between trades for same ticker

### 6. Idempotency
- Generates deterministic `execution_id` from opportunity
- Uses Redis SETNX to prevent duplicate orders
- TTL: 24 hours

### 7. Rate Limiting & Fail Safe
- API errors don't crash the service
- Rejected orders logged with status "REJECTED"
- Network errors logged with status "ERROR"

## Inputs

- **Subscribe:** `chan:opportunity_update` (OpportunityRank payload)
- **Read:** 
  - `key:market_state` (for veto check)
  - `key:execution_enabled` (kill switch)

## Outputs

### Redis Pub/Sub
- **Channel:** `chan:trade_update`
- **Payload:** Trade execution event with:
  - `execution_id`
  - `status`: SUBMITTED | BLOCKED | SKIPPED | REJECTED | ERROR
  - `alpaca_order_id` (if submitted)
  - `why[]` (reasons)
  - `market_state_snapshot`

### Database
- **Table:** `execution_log`
- Writes all events (including BLOCKED/SKIPPED) for audit trail

## Running

### Enable Execution (Kill Switch)

```bash
# Enable execution
docker compose --env-file .env -f infra/docker-compose.yml exec redis redis-cli SET key:execution_enabled "true"

# Disable execution (safety)
docker compose --env-file .env -f infra/docker-compose.yml exec redis redis-cli SET key:execution_enabled "false"
```

### Start Service

```bash
docker compose --env-file .env -f infra/docker-compose.yml up -d zero-execution
```

### Health Check

```bash
curl http://localhost:8003/health
```

## Configuration

**Required Environment Variables:**
- `ALPACA_API_KEY` - Alpaca API key
- `ALPACA_SECRET_KEY` - Alpaca secret key
- `ALPACA_PAPER=true` - **MUST be true** (service exits if false)

**Optional:**
- `REDIS_HOST` (default: `redis`)
- `REDIS_PORT` (default: `6379`)
- `EXECUTION_API_PORT` (default: `8003`)

## Acceptance Criteria

✅ Service refuses to start if `ALPACA_PAPER != true`  
✅ With `key:execution_enabled` missing/false → NO ORDERS EVER  
✅ With `market_state != GREEN` → NO ORDERS EVER  
✅ Duplicate opportunity messages do NOT create duplicate orders  
✅ Creates `execution_log` rows and publishes `chan:trade_update` payloads

## Architecture

- **Framework:** Python asyncio
- **Alpaca SDK:** `alpaca-py` (synchronous, wrapped in `asyncio.to_thread`)
- **Port:** 8003
- **Dependencies:** Redis, TimescaleDB (optional), Alpaca API

## Safety Philosophy

**ZERO is a Decision Support System, not a trading bot.**

Execution is:
- **Opt-in** (kill switch default OFF)
- **Paper-only** (hard enforced)
- **Audited** (all events logged)
- **Idempotent** (no duplicate orders)
- **Rate-limited** (cooldowns and position limits)
