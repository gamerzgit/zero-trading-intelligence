# ZERO Regime Engine Service (Milestone 2)

**Level 0: Market Permission (Veto Layer)**

## Purpose

The Regime Engine determines **Market Permission** - the foundational veto layer that can halt all trading activity, but never approve alone.

## Features

- **NYSE Calendar Integration**: Uses `pandas_market_calendars` for accurate market hours, holidays, and early closes
- **VIX/Volatility Detection**: Fetches VIX via VIXY ETF proxy (labeled clearly)
- **Time Window Detection**: Prime Window, Opening, Lunch, Closing windows
- **State Management**: GREEN/YELLOW/RED states with standardized reasons
- **Redis Integration**: Publishes state changes, stores current state
- **Database Persistence**: Logs state changes to `regime_log` table

## Market States

### RED (Halt)
- Weekend
- Market Holiday
- Off Hours (before open/after close)
- Volatility >= 25 (FEAR/PANIC)
- Event Risk

### YELLOW (Caution)
- Opening Window (9:30-10:30 ET)
- Lunch Window (11:00-13:00 ET)
- Volatility 20-25 (ELEVATED)

### GREEN (Full Permission)
- Prime Window (13:00-15:00 ET) + Low Volatility
- Closing Window (15:00-close ET) + Low Volatility

## Time Windows

- **OPENING**: 09:30-10:30 ET (High volatility, choppy)
- **LUNCH**: 11:00-13:00 ET (Low volume, avoid)
- **PRIME_WINDOW**: 13:00-15:00 ET (Optimal liquidity period - ZERO proprietary)
- **CLOSING**: 15:00-session_close ET (Gamma/closing flows)

## Standardized Reasons

- "Weekend Halt"
- "Market Holiday Halt"
- "Off Hours Halt"
- "Opening Volatility"
- "Lunch Chop"
- "Prime Window"
- "Closing Window"
- "Volatility Halt (>=25) [VIX Proxy (VIXY)=X.XX]"
- "Elevated Volatility (20-25) [VIX Proxy (VIXY)=X.XX]"

## API

### Health Endpoint

```
GET /health
```

Returns current MarketState and service status.

## Configuration

Environment variables:
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- `REDIS_HOST`, `REDIS_PORT`
- `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` (for VIX proxy)
- `REGIME_API_PORT` (default: 8000)

## Redis

- **Key**: `key:market_state` - Full MarketState JSON
- **Channel**: `chan:market_state_changed` - StateChangeNotification (not full state)

## Database

- **Table**: `regime_log`
- **Writes**: Only on state changes (not every minute)

## Docker

```bash
# Build and start
docker compose -f infra/docker-compose.yml up zero-regime

# Check logs
docker compose -f infra/docker-compose.yml logs -f zero-regime

# Health check
curl http://localhost:8000/health
```

## Architecture

```
RegimeService
├── RegimeCalculator (logic.py)
│   ├── NYSE Calendar (pandas_market_calendars)
│   ├── Time Window Detection
│   └── Market State Calculation
├── VolatilityProxy (vol_proxy.py)
│   └── VIX/VIXY Fetching
└── Main Loop
    ├── Calculate state every 60s
    ├── Publish to Redis on change
    └── Persist to DB on change
```

## Notes

- Uses ZERO-native terminology only (Prime Window, not external names)
- VIXY proxy is clearly labeled in reason text
- State changes trigger Redis notification + DB write
- Full state stored in Redis key, notification is lightweight

