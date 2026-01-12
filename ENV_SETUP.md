# Environment Variables Setup Guide

## Quick Reference

### For Standalone Validation (`verify_system_standalone.py`)

**Minimum required:**
- `ALPACA_API_KEY` - Your Alpaca API key
- `ALPACA_SECRET_KEY` - Your Alpaca secret key
- `ALPACA_PAPER=true` - Use paper trading account

**Optional (for full tests):**
- `DB_HOST`, `DB_PASSWORD`, `REDIS_HOST` - Only if testing DB/Redis connectivity

### For Full System (`make up` + `verify_state.py`)

**Required:**
- `ALPACA_API_KEY` - For data ingestion
- `ALPACA_SECRET_KEY` - For data ingestion
- `DB_PASSWORD` - TimescaleDB password (must match POSTGRES_PASSWORD)
- `POSTGRES_PASSWORD` - TimescaleDB password (must match DB_PASSWORD)
- `GRAFANA_ADMIN_PASSWORD` - Grafana admin password

**Optional:**
- `PROVIDER_TYPE` - Set to "alpaca" (default: "mock")
- `SCAN_INTERVAL_SECONDS` - Scanner interval (default: 60)

## File Location

The `.env` file should be in the project root:
```
~/zero-trading-intelligence/.env
```

## Security Notes

⚠️ **IMPORTANT:**
- `.env` is in `.gitignore` - it will NOT be committed to git
- Never share your API keys publicly
- Use strong passwords for database and Grafana
- On Jetson, ensure `.env` has proper permissions: `chmod 600 .env`

## Setup Steps

1. **Copy the example file:**
   ```bash
   cp .env.example .env
   ```

2. **Edit with your credentials:**
   ```bash
   nano .env
   # or use your preferred editor
   ```

3. **Fill in required values:**
   - Alpaca API keys (for data ingestion)
   - Database password (choose a secure password)
   - Grafana password (choose a secure password)

4. **Verify the file:**
   ```bash
   # Check file exists and has correct permissions
   ls -la .env
   # Should show: -rw------- (600 permissions)
   ```

## Testing Your .env File

**Standalone validation:**
```bash
python scripts/verify_system_standalone.py
# Should show: ✅ Loaded .env from /path/to/.env
```

**Full system (after make up):**
```bash
python scripts/verify_state.py
# Should connect to all services using .env values
```

## Troubleshooting

**"Warning: .env file not found"**
- Make sure you're in the project root directory
- Check file exists: `ls -la .env`
- Verify path: `pwd` should show `~/zero-trading-intelligence`

**"Alpaca credentials not found"**
- Check `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` are set
- No quotes needed around values
- No spaces around `=` sign

**"Database connection failed"**
- For standalone: This is OK (standalone doesn't need DB)
- For full system: Check `DB_PASSWORD` matches `POSTGRES_PASSWORD`
- Verify Docker services are running: `make status`
