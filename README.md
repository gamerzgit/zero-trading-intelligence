# ZERO Trading Intelligence Platform

**Version:** Milestone 2 (Regime Engine)  
**Last Updated:** 2026-01-11

A probabilistic market intelligence platform (Decision Support System) running on NVIDIA Jetson Orin AGX.

---

## 🎯 What is ZERO?

ZERO is a **Quantitative Decision Support System (QDSS)** that provides:
- Market regime "permission" state (veto layer)
- Market attention/narrative dominance analysis
- Opportunity discovery and ranking across horizons
- Probabilistic opportunity outputs (not price targets)
- "What NOT to trade today" guidance

**ZERO is NOT:**
- ❌ A trading bot (no automated execution)
- ❌ A deterministic price predictor
- ❌ A guarantee system

**ZERO is:**
- ✅ A decision support system
- ✅ Probabilistic and explainable
- ✅ Regime-conditioned
- ✅ Self-learning (truth test loop)

**Note:** Milestones 0-2 complete. Level 0 (Market Permission/Veto) is operational. Scanner and ranking engines coming in future milestones.

---

## 🏗️ Milestone Status

### Milestone 0: Architecture & Contracts ✅ COMPLETE
- ✅ Database schema (TimescaleDB)
- ✅ Redis contracts (keys, channels, streams)
- ✅ Pydantic schemas (Python models)
- ✅ API contract (HTTP endpoints)
- ✅ Docker Compose infrastructure
- ✅ Grafana provisioning

### Milestone 1: Price Ingestion ✅ COMPLETE
- ✅ `zero-ingest-price` service implemented
- ✅ Provider abstraction (Mock + Polygon + Alpaca)
- ✅ Database writers (1m, 5m, 1d candles)
- ✅ Redis event publishing
- ✅ Health endpoint (`/health`)
- ✅ Gap detection and logging
- ✅ Auto-aggregation (5m from 1m, 1d from 1m)

**Current Symbols:** SPY, QQQ, IWM, AAPL, MSFT

### Milestone 2: Regime Engine (Level 0) ✅ COMPLETE
- ✅ `zero-regime` service implemented
- ✅ NYSE market hours detection (pandas-market-calendars)
- ✅ Time window classification (OPENING, LUNCH, PRIME_WINDOW, CLOSING)
- ✅ Volatility zones (GREEN/YELLOW/RED based on VIX/VIXY)
- ✅ Market state calculation (GREEN/YELLOW/RED veto logic)
- ✅ Redis state storage (`key:market_state`)
- ✅ State change notifications (`chan:market_state_changed`)
- ✅ Database persistence (`regime_log` table)
- ✅ Health endpoint (`/health` on port 8000)
- ✅ Weekend/holiday detection (automatic RED/Halt)

**What's NOT Included (Future Milestones):**
- ❌ Scanner engine (Level 2)
- ❌ Opportunity ranking (Level 3)
- ❌ Attention/Narrative engine (Level 1)
- ❌ Trading execution

---

## 🚀 Quick Start (Milestone 0)

### Prerequisites

- **Hardware:** NVIDIA Jetson Orin AGX (ARM64)
- **OS:** Ubuntu 22.04 LTS (JetPack 6.x)
- **Storage:** 1TB NVMe SSD mounted
- **Software:**
  - Docker & Docker Compose
  - NVIDIA Container Toolkit
  - Make (optional, for convenience)

**CRITICAL - Storage Location:**
- Ensure `data_nvme/` is located on NVMe mount (example: `/mnt/nvme/zero/data_nvme`)
- **Do NOT store DB volumes on eMMC** (will degrade hardware)
- If using `./data_nvme` relative path, ensure the repository folder itself is on NVMe

### Setup Steps

1. **Clone/Download Project**
   ```bash
   cd ~
   # Transfer project to Jetson (Git, SCP, or USB)
   cd zero-trading-intelligence
   ```

2. **Set Jetson to MAXN Mode (CRITICAL)**
   ```bash
   sudo nvpmodel -m 0
   sudo jetson_clocks  # Recommended but optional
   ```

3. **Configure Environment**
   ```bash
   cp .env.example .env
   nano .env  # Edit with your passwords
   ```

4. **Create Data Directories**
   ```bash
   mkdir -p data_nvme/{timescaledb,redis,grafana}
   ```

5. **Start Services**
   ```bash
   make up
   # Or manually:
   # docker compose -f infra/docker-compose.yml up -d
   ```

5. **Verify Services**
   ```bash
   make status
   # Check logs:
   make logs
   ```

6. **Access Grafana**
   - Open browser: `http://<jetson-ip>:3000`
   - Login: `admin` / `<GRAFANA_ADMIN_PASSWORD>`
   - Grafana datasource is auto-provisioned via `infra/grafana/provisioning/datasources/`
   - TimescaleDB datasource should appear automatically

7. **Validate Database**
   ```bash
   make psql
   # In psql:
   # \dt  # List tables
   # SELECT * FROM timescaledb_information.hypertables;
   # \q   # Exit
   ```

8. **Verify Ingestion Service (Milestone 1)**
   ```bash
   # Check service status
   make status
   
   # Check health endpoint
   curl http://localhost:8080/health
   
   # Check logs
   docker compose -f infra/docker-compose.yml logs zero-ingest-price
   
   # Verify data is being ingested
   make psql
   # In psql:
   # SELECT COUNT(*) FROM candles_1m;
   # SELECT ticker, MAX(time) FROM candles_1m GROUP BY ticker;
   ```

9. **Verify Regime Engine Service (Milestone 2)**
   ```bash
   # Check service status
   make status
   
   # Check health endpoint
   curl http://localhost:8000/health
   
   # Check logs
   docker compose -f infra/docker-compose.yml logs zero-regime
   
   # Verify regime state in Redis
   make redis-cli
   # In redis-cli:
   # GET key:market_state
   # PUBSUB CHANNELS chan:*
   ```

10. **Run Comprehensive Verification Script**
   ```bash
   # Install verification script dependencies
   pip install -r scripts/requirements.txt
   
   # Run standalone verification (Windows/local - no Docker required)
   python scripts/verify_system_standalone.py
   
   # Run full system verification (requires Docker services running)
   python scripts/verify_system.py
   ```
   
   **Note:** Ensure your `.env` file contains Alpaca credentials:
   ```bash
   ALPACA_API_KEY=your_key_here
   ALPACA_SECRET_KEY=your_secret_here
   ALPACA_PAPER=true
   ```

---

## 📁 Project Structure

```
zero-trading-intelligence/
├── contracts/              # Frozen contracts (schema, Redis, API)
│   ├── schemas.py         # Pydantic models
│   ├── redis_keys.md      # Redis keys & channels
│   ├── db_schema.md       # Database schema
│   └── api_contract.md    # HTTP API definition
├── docs/                  # Documentation
│   └── SPEC_LOCK.md       # Constitution (non-negotiable rules)
├── infra/                 # Infrastructure
│   ├── docker-compose.yml # Docker services
│   ├── db/
│   │   └── init.sql       # Database initialization
│   └── grafana/
│       └── provisioning/  # Grafana auto-config
├── services/              # Microservices
│   ├── ingest/            # Price ingestion service (M1)
│   └── regime/            # Regime engine service (M2)
├── scripts/               # Utility scripts
├── data_nvme/             # Data storage (gitignored)
├── .env.example           # Environment template
├── Makefile               # Convenience commands
├── .gitignore
└── README.md
```

---

## 🔧 Makefile Commands

```bash
make up          # Start all services
make down        # Stop all services
make logs        # View logs
make psql        # Connect to TimescaleDB
make redis-cli   # Connect to Redis
make restart     # Restart services
make status      # Show service status
make clean       # Remove all data (WARNING! Deletes ./data_nvme - irreversible)
```

**Note:** Makefile uses `docker compose` (modern CLI). You can also use commands directly:
```bash
docker compose -f infra/docker-compose.yml up -d
docker compose -f infra/docker-compose.yml ps
docker compose -f infra/docker-compose.yml logs timescaledb
```

---

## 🗄️ Database

**TimescaleDB (PostgreSQL extension)**

- **Connection (from Docker):** `timescaledb:5432`
- **Connection (from host):** `localhost:5432`
- **Database:** `zero_trading`
- **User:** `zero_user`
- **Password:** From `.env` file

**Tables:**
- `candles_1m`, `candles_5m`, `candles_1d` (hypertables)
- `ticks` (hypertable, 7-day retention)
- `regime_log`, `attention_log` (hypertables)
- `opportunity_log`, `performance_log`
- `ingest_gap_log`

**Retention Policies:**
- Ticks: 7 days
- 1-minute candles: 1 year
- 5-minute & daily: Forever

---

## 🔴 Redis

**Connection (from Docker):** `redis:6379`  
**Connection (from host):** `localhost:6379`

**Key Naming:**
- Keys: `key:<name>`
- Channels: `chan:<name>`
- Streams: `stream:<name>`

**State Storage Rules (Contract):**
- **State lives ONLY in Redis key-value stores** (`key:*`)
- **Pub/Sub has two types of channels:**
  1) **Event channels (full payload)** e.g. `chan:ticker_update`, `chan:news_raw`
  2) **State-change notification channels (minimal payload)** e.g. `chan:*_state_changed` that reference the updated `key:*`
- Grafana reads ONLY from TimescaleDB (never Redis)

---

## 📊 Grafana

**Access:** `http://<jetson-ip>:3000`

**Default Credentials:**
- User: `admin`
- Password: From `.env` (`GRAFANA_ADMIN_PASSWORD`)

**Auto-Provisioned:**
- TimescaleDB datasource (via `infra/grafana/provisioning/datasources/timescaledb.yml`)
- Dashboard provider (via `infra/grafana/provisioning/dashboards/default.yml`)

**Expected First-Run Behavior:**
- TimescaleDB runs `init.sql`, creates hypertables + policies
- Grafana provisions datasource automatically
- No dashboards may appear yet (empty for M0)

---

## 🔍 Validation

### Milestone 0 Validation

### Check Database Initialization

```bash
make psql
```

In psql:
```sql
-- List all tables
\dt

-- Check hypertables
SELECT * FROM timescaledb_information.hypertables;

-- Check all jobs (retention + compression)
SELECT * FROM timescaledb_information.jobs;

-- Check retention policies specifically
SELECT * FROM timescaledb_information.jobs WHERE proc_name LIKE '%retention%';

-- Check compression policies specifically
SELECT * FROM timescaledb_information.jobs WHERE proc_name LIKE '%compression%';

-- Check compression settings
SELECT * FROM timescaledb_information.compression_settings;

-- Verify tables exist
SELECT COUNT(*) FROM candles_1m;
SELECT COUNT(*) FROM regime_log;
```

### Check Redis

```bash
make redis-cli
```

In redis-cli:
```redis
PING  # Should return PONG
KEYS *  # Should be empty (no data yet)
```

### Check Services

```bash
make status
docker compose -f infra/docker-compose.yml ps
```

All services should show "Up" status.

### Milestone 1 Validation (Price Ingestion)

**Check Ingestion Service:**
```bash
# Health check
curl http://localhost:8080/health

# Expected response:
# {
#   "service": "zero-ingest-price",
#   "status": "healthy",
#   "details": {
#     "provider_connected": true,
#     "database_connected": true,
#     "redis_connected": true,
#     "last_candles": {...}
#   }
# }
```

**Verify Data Ingestion:**
```bash
make psql
```

In psql:
```sql
-- Check 1-minute candles
SELECT ticker, COUNT(*) as count, MIN(time) as first, MAX(time) as last
FROM candles_1m
GROUP BY ticker;

-- Check 5-minute aggregation
SELECT ticker, COUNT(*) as count
FROM candles_5m
GROUP BY ticker;

-- Check daily aggregation
SELECT ticker, COUNT(*) as count
FROM candles_1d
GROUP BY ticker;

-- Check for gaps
SELECT ticker, COUNT(*) as gap_count
FROM ingest_gap_log
WHERE backfilled = false
GROUP BY ticker;
```

**Check Redis Events:**
```bash
make redis-cli
```

In redis-cli:
```redis
PUBSUB CHANNELS chan:*
# Should show: chan:ticker_update, chan:index_update
```

### Milestone 2 Validation (Regime Engine)

**Check Regime Service:**
```bash
# Health check
curl http://localhost:8000/health

# Expected response:
# {
#   "service": "zero-regime",
#   "status": "healthy",
#   "market_state": {
#     "state": "GREEN" | "YELLOW" | "RED",
#     "vix_level": 16.5,
#     "reason": "Prime Window",
#     "timestamp": "2026-01-11T14:00:00-05:00"
#   }
# }
```

**Verify Regime State in Redis:**
```bash
make redis-cli
```

In redis-cli:
```redis
# Get current market state
GET key:market_state

# Check state change channel
PUBSUB CHANNELS chan:*
# Should show: chan:market_state_changed
```

**Verify Regime Log in Database:**
```bash
make psql
```

In psql:
```sql
-- Check regime log entries
SELECT state, reason, vix_level, created_at
FROM regime_log
ORDER BY created_at DESC
LIMIT 10;

-- Check state distribution
SELECT state, COUNT(*) as count
FROM regime_log
GROUP BY state;
```

### Ports Used

- **TimescaleDB:** 5432
- **Redis:** 6379
- **Grafana:** 3000
- **Ingestion Service:** 8080
- **Regime Engine Service:** 8000

### Health Checks

```bash
# Ingestion service
curl http://localhost:8080/health

# Regime engine service
curl http://localhost:8000/health
```

---

## 📚 Documentation

- **SPEC_LOCK.md** - Constitution (non-negotiable rules)
- **contracts/db_schema.md** - Database schema
- **contracts/redis_keys.md** - Redis contracts
- **contracts/api_contract.md** - HTTP API
- **contracts/schemas.py** - Pydantic models

---

## 🐛 Troubleshooting

### Database Connection Failed

```bash
# Check if TimescaleDB is running
docker compose -f infra/docker-compose.yml ps timescaledb

# Check logs
docker compose -f infra/docker-compose.yml logs timescaledb

# Verify environment variables
cat .env | grep POSTGRES
```

### Redis Connection Failed

```bash
# Check if Redis is running
docker compose -f infra/docker-compose.yml ps redis

# Check logs
docker compose -f infra/docker-compose.yml logs redis
```

### Grafana Not Loading

```bash
# Check if Grafana is running
docker compose -f infra/docker-compose.yml ps grafana

# Check logs
docker compose -f infra/docker-compose.yml logs grafana

# Verify datasource provisioning
docker compose -f infra/docker-compose.yml exec grafana ls -la /etc/grafana/provisioning/datasources
```

### Permission Errors (Data Directories)

```bash
# Fix permissions
sudo chown -R $USER:$USER data_nvme/
chmod -R 755 data_nvme/
```

---

## 🚧 Next Steps (Future Milestones)

- ✅ **Milestone 0:** Architecture & Contracts
- ✅ **Milestone 1:** Price ingestion service
- ✅ **Milestone 2:** Regime engine (Level 0)
- **Milestone 3:** Scanner (Level 2) - Opportunity Discovery
- **Milestone 4:** Core logic (Level 3) - Opportunity Ranking
- **Milestone 5:** Narrative LLM (Level 1) - Attention & Narrative
- **Milestone 6:** Truth test & learning loop

---

## 📝 License

[To be determined]

---

## 🤝 Contributing

[To be determined]

---

**END OF README**

