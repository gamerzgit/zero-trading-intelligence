# ZERO Verification Scripts

This directory contains verification scripts for the ZERO Trading Intelligence Platform.

## Scripts Overview

### 1. `verify_system_standalone.py` - Code & Contract Validation

**Purpose:** Validates code structure, contracts, and Alpaca connectivity **without requiring Docker services**.

**What it checks:**
- ✅ Module imports (asyncpg, redis, alpaca-py, aiohttp, pydantic, etc.)
- ✅ Project file structure
- ✅ Environment variables
- ✅ Alpaca API connectivity (authentication + data retrieval)
- ✅ Provider code (Mock, Alpaca, Polygon)
- ✅ Database writer code structure
- ✅ Redis publisher code structure
- ✅ Pydantic schemas validation
- ✅ Integration test (mock pipeline)
- ✅ Regime Engine code (Milestone 2) - **FAILS if pandas-market-calendars missing**
- ✅ Scanner Engine code (Milestone 3)

**Usage:**
```bash
# From project root
python scripts/verify_system_standalone.py
```

**When to use:**
- Development environment (before deploying to Jetson)
- Local code validation
- CI/CD pipeline (code quality checks)
- Before committing code changes

**Exit codes:**
- `0` - All tests passed
- `1` - One or more tests failed

**Note:** This does **NOT** mean Milestones 0-3 are operational end-to-end. It proves:
- Code loads correctly
- Schemas are valid
- Alpaca authentication works
- Mock pipeline works

---

### 2. `verify_state.py` - Full System Verification

**Purpose:** Comprehensive validation that Milestones 0-3 are **operational end-to-end** on a running system.

**What it checks:**

**Milestone 0: Infrastructure**
- ✅ Docker services running (timescaledb, redis, grafana, zero-ingest-price, zero-regime, zero-scanner)
- ✅ Redis connectivity
- ✅ TimescaleDB connectivity
- ✅ Database schema integrity (tables + hypertables)

**Milestone 1: Ingestion Service**
- ✅ Service health endpoint (`/health` on port 8080)
- ✅ Ingestion freshness (market calendar aware)
- ✅ Gap detection (unbackfilled gaps)

**Milestone 2: Regime Engine**
- ✅ Service health endpoint (`/health` on port 8000)
- ✅ Redis contracts (keys + channels)
- ✅ Redis state validation (`key:market_state`)
- ✅ Database logging (`regime_log` table)
- ✅ Logic consistency (weekend/holiday → RED state)

**Milestone 3: Scanner Engine**
- ✅ Service health endpoint (`/health` on port 8001)
- ✅ Veto-aware behavior (RED state handling)
- ✅ Redis outputs validation (`key:active_candidates`)
- ✅ Database logging (`scanner_log` table, NOT `opportunity_log`)
- ✅ No Level 3 fields (no ranking/probability)

**Usage:**
```bash
# From project root (with Docker services running)
python scripts/verify_state.py
```

**When to use:**
- After `make up` on Jetson
- Before proceeding to Milestone 4
- System health checks
- Production deployment validation

**Prerequisites:**
- Docker services must be running (`make up`)
- All services must be healthy
- Database must be initialized
- Redis must be running

**Exit codes:**
- `0` - All checks passed (or warnings only)
- `1` - One or more checks failed

**Output:**
- ✅ PASS - Check passed
- ⚠️ WARN - Warning (doesn't fail, but should be reviewed)
- ❌ FAIL - Failure (exits with code 1)

**Final message:**
- `✅ SYSTEM READY FOR MILESTONE 4` - All checks passed
- `❌ SYSTEM NOT READY - Fix failures before proceeding` - One or more failures

---

### 3. `verify_system.py` - Legacy/Alternative System Verification

**Note:** This may be an older version. Use `verify_state.py` for comprehensive system verification.

---

## Quick Reference

### Development Workflow

1. **Before committing code:**
   ```bash
   python scripts/verify_system_standalone.py
   ```
   Ensures code structure is valid.

2. **After deploying to Jetson:**
   ```bash
   make up  # Start services
   python scripts/verify_state.py  # Verify system is operational
   ```

### Troubleshooting

**verify_system_standalone.py fails:**
- Check Python dependencies: `pip install -r scripts/requirements.txt`
- Check Alpaca credentials in `.env`
- Check pandas-market-calendars is installed (for regime tests)

**verify_state.py fails:**
- Ensure Docker services are running: `make status`
- Check service logs: `make logs`
- Verify database is initialized: `make psql`
- Check Redis is running: `make redis-cli`

---

## Dependencies

All scripts require:
- Python 3.8+
- Dependencies from `requirements.txt`:
  - `asyncpg>=0.29.0`
  - `redis>=5.0.0`
  - `alpaca-py>=0.42.0`
  - `python-dotenv>=1.0.0`
  - `aiohttp>=3.9.0`
  - `pandas-market-calendars>=4.3.0` (for market calendar checks)
  - `pytz>=2023.3`

Install:
```bash
pip install -r scripts/requirements.txt
```
