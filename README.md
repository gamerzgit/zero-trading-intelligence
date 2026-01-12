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
- ✅ Designed for calibration via truth testing (implemented in future milestones)

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
- ❌ Attention/Narrative engine (Level 1)
- ❌ Scanner engine (Level 2)
- ❌ Opportunity ranking / Probability engine (Level 3)
- ❌ Trading execution

---

## 🚀 Quick Start (Milestones 0-2)

### Prerequisites

- **Hardware:** NVIDIA Jetson Orin AGX (ARM64)
- **OS:** Ubuntu 22.04 LTS (JetPack 6.2 rev 2)
- **Storage:** 1TB NVMe SSD mounted
- **Software:**
  - Docker & Docker Compose
  - NVIDIA Container Toolkit
  - Make (optional, for convenience)

---

## 📦 First Time Installation Guide

**If this is your first time setting up ZERO on your Jetson, follow these steps:**

### Step 1: Install JetPack 6.2 rev 2 (If Not Already Installed)

1. **Download SDK Manager** from NVIDIA Developer Portal
2. **Connect your Jetson Orin AGX** via USB-C to your host machine
3. **Select Components:**
   - ✅ Jetson Linux
   - ✅ Sample Root Filesystem (Ubuntu 22.04)
   - ✅ CUDA Toolkit
   - ✅ TensorRT
   - ✅ cuDNN
   - ✅ **Jetson Platform Services** (IMPORTANT)
   - ❌ Skip: DeepStream, VisionWorks, Multimedia API, VPI
4. **Flash the Jetson** and complete initial setup

### Step 2: Initial Jetson Configuration

**SSH into your Jetson:**
```bash
ssh jetson@<jetson-ip-address>
```

**Update system:**
```bash
sudo apt update
sudo apt upgrade -y
```

**Set to MAXN Power Mode (CRITICAL):**
```bash
sudo nvpmodel -m 0
sudo jetson_clocks
```

**Verify power mode:**
```bash
sudo nvpmodel -q  # Should show "MODE: 0 (MAXN)"
```

### Step 3: Install Docker & Docker Compose

**Install Docker:**
```bash
# Add Docker's official GPG key
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add Docker repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add your user to docker group (to run without sudo)
sudo usermod -aG docker $USER
newgrp docker  # Apply group change

# Verify Docker installation
docker --version
docker compose version
```

**Note:** You may need to log out and back in for the docker group to take effect.

### Step 4: Install NVIDIA Container Toolkit

**Install NVIDIA Container Toolkit:**
```bash
# Add NVIDIA package repositories
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list

# Install nvidia-container-toolkit
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# Configure Docker to use NVIDIA runtime
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Verify NVIDIA Container Toolkit
docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi
```

### Step 5: Install Make (Optional but Recommended)

```bash
sudo apt-get install -y make
```

### Step 6: Install Jetson Stats (Optional but Recommended)

```bash
sudo pip3 install -U jetson-stats
sudo systemctl restart jtop  # If installed
# Run: jtop  # To view system stats
```

### Step 7: Clone/Download ZERO Project

**Clone the repository:**
```bash
cd ~
git clone https://github.com/gamerzgit/zero-trading-intelligence.git
cd zero-trading-intelligence
```

**Or if transferring manually:**
```bash
# Transfer project files to Jetson (via SCP, USB, etc.)
cd ~
# Extract/unzip to: ~/zero-trading-intelligence
cd zero-trading-intelligence
```

### Step 8: Configure Environment Variables

**Create `.env` file:**
```bash
cp .env.example .env
nano .env  # Or use your preferred editor
```

**Required variables (minimum):**
```bash
# Database
DB_PASSWORD=your_secure_password_here
DB_USER=zero_user
DB_NAME=zero_trading

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Data Provider (choose ONE)
# Option 1: Alpaca
PROVIDER_TYPE=alpaca
ALPACA_API_KEY=your_alpaca_key_here
ALPACA_SECRET_KEY=your_alpaca_secret_here
ALPACA_PAPER=true

# Option 2: Polygon
# PROVIDER_TYPE=polygon
# POLYGON_API_KEY=your_polygon_key_here

# Grafana
GRAFANA_ADMIN_PASSWORD=your_grafana_password_here
```

**Save and exit** (Ctrl+X, then Y, then Enter in nano)

### Step 9: Create Data Directories

**CRITICAL - Use NVMe storage (NOT eMMC):**

```bash
# Option 1: If NVMe is mounted at /mnt/nvme
sudo mkdir -p /mnt/nvme/zero/data_nvme/{timescaledb,redis,grafana}
sudo chown -R $USER:$USER /mnt/nvme/zero/data_nvme
cd ~/zero-trading-intelligence
ln -s /mnt/nvme/zero/data_nvme data_nvme

# Option 2: If project is on NVMe already
mkdir -p data_nvme/{timescaledb,redis,grafana}
```

**Verify storage location:**
```bash
df -h data_nvme/  # Should show NVMe device, not eMMC
```

### Step 10: Start Services

**Start all services:**
```bash
make up
# Or manually:
# docker compose -f infra/docker-compose.yml up -d
```

**Check service status:**
```bash
make status
# Or:
# docker compose -f infra/docker-compose.yml ps
```

**View logs (if needed):**
```bash
make logs
# Or:
# docker compose -f infra/docker-compose.yml logs -f
```

### Step 11: Verify Installation

**Wait 30-60 seconds for services to start, then verify:**

**Check TimescaleDB:**
```bash
make psql
# In psql, run:
# \dt  # Should show tables
# \q   # Exit
```

**Check Redis:**
```bash
make redis-cli
# In redis-cli, run:
# PING  # Should return PONG
# exit
```

**Check service health:**
```bash
# Ingestion service
curl http://localhost:8080/health

# Regime engine service
curl http://localhost:8000/health
```

**Access Grafana:**
- Open browser: `http://<jetson-ip>:3000`
- Login: `admin` / `<GRAFANA_ADMIN_PASSWORD>`

### Step 12: Run Verification Script

**Install verification dependencies:**
```bash
pip3 install -r scripts/requirements.txt
```

**Run verification:**
```bash
python3 scripts/verify_system_standalone.py
```

---

**✅ Installation Complete!** 

You can now proceed to the regular **Quick Start** section below for ongoing operations.
  
**JetPack 6.2 Installation Guide (SDK Manager):**

**During JetPack Installation - What to Select:**

1. **✅ SELECT - Core Components (Usually Default):**
   - ✅ **Jetson Linux** - Required (base OS)
   - ✅ **Sample Root Filesystem** - Required (Ubuntu 22.04)
   - ✅ **CUDA Toolkit** - Required (for future ML model GPU acceleration)
   - ✅ **TensorRT** - Required (for future ML model optimization)
   - ✅ **cuDNN** - Required (for deep learning operations)
   - ✅ **Jetson Platform Services** - **SELECT THIS** (system monitoring, power management, MAXN mode support)

2. **❌ SKIP - Optional SDK Components (Not Needed for ZERO):**
   - ❌ **DeepStream SDK** - Skip (video analytics not required)
   - ❌ **VisionWorks** - Skip (computer vision not required)
   - ❌ **Multimedia API** - Skip (video/audio processing not required)
   - ❌ **VPI (Vision Programming Interface)** - Skip

**Post-Installation (Optional but Recommended):**
- ✅ **Jetson Stats** - Install separately: `sudo pip3 install -U jetson-stats` (system health monitoring)

**Note:** 
- For Milestones 0-2 (current), base JetPack is sufficient
- TensorRT/CUDA are included by default and will be needed for future milestones (ML models, LLM inference)
- **Platform Services are essential** - make sure to select them during installation

**CRITICAL - Storage Location:**
- Ensure `data_nvme/` is located on NVMe mount (example: `/mnt/nvme/zero/data_nvme`)
- **Do NOT store DB volumes on eMMC** (will degrade hardware)
- If using `./data_nvme` relative path, ensure the repository folder itself is on NVMe

### Setup Steps (If Already Installed - Skip to Step 8)

**Note:** If this is your first time, see **"First Time Installation Guide"** section above.

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
   
   **Note:** Ensure your `.env` file contains the credentials required by your selected provider:
   
   **For Alpaca:**
   ```bash
   ALPACA_API_KEY=your_key_here
   ALPACA_SECRET_KEY=your_secret_here
   ALPACA_PAPER=true
   ```
   
   **For Polygon:**
   ```bash
   POLYGON_API_KEY=your_key_here
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

### Market Hours vs Off-Hours Behavior

**Services run 24/7:**
- All Docker services remain running continuously
- The Jetson stays operational even when markets are closed

**During Market Hours (9:30 AM - 4:00 PM ET, weekdays):**
- Ingestion service streams live market data
- Regime engine updates market state every minute
- Market state can be GREEN, YELLOW, or RED based on conditions

**During Off-Hours / Weekends / Holidays:**
- Market state automatically set to RED (Halt)
- Ingestion service may be idle or perform backfill operations
- Services continue running and monitoring for market open

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
- **Milestone 3:** Attention Engine (Level 1) - Attention state (score-based) + dominance signals
- **Milestone 4:** Scanner (Level 2) - Candidate discovery
- **Milestone 5:** Probability Engine (Level 3) - Ranking + probabilities
- **Milestone 6:** Narrative Engine (Level 1b) + Truth Test & Calibration loop

---

## 📝 License

[To be determined]

---

## 🤝 Contributing

[To be determined]

---

**END OF README**

