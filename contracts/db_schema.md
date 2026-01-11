# Database Schema Contract

**Version:** 1.0  
**Last Updated:** 2026-01-11

**Database:** TimescaleDB (PostgreSQL extension)  
**Location:** `./data_nvme/timescaledb`

---

## TABLE DEFINITIONS

### 1. `candles_1m` (1-Minute Candles)

**Purpose:** Store 1-minute OHLCV candles for all tickers  
**Type:** TimescaleDB Hypertable  
**Retention:** DROP chunks older than 1 year  
**Compression:** Enabled for chunks >24 hours

| Column Name | Type | Constraints | Description |
|------------|------|-------------|-------------|
| `ticker` | VARCHAR(10) | PRIMARY KEY, NOT NULL | Stock symbol (e.g., 'SPY', 'AAPL') |
| `time` | TIMESTAMPTZ | PRIMARY KEY, NOT NULL | Timestamp (1-minute resolution) |
| `open` | DOUBLE PRECISION | NOT NULL | Opening price |
| `high` | DOUBLE PRECISION | NOT NULL | High price |
| `low` | DOUBLE PRECISION | NOT NULL | Low price |
| `close` | DOUBLE PRECISION | NOT NULL | Closing price |
| `volume` | BIGINT | NOT NULL | Volume |
| `vwap` | DOUBLE PRECISION | NULL | Volume-weighted average price |
| `source` | VARCHAR(32) | NOT NULL DEFAULT 'unknown' | Data source provider |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Record creation timestamp |

**Indexes:**
- Primary key: `(ticker, time)` (composite, ticker first for query optimization)
- Index on `time` for time-range queries

---

### 2. `candles_5m` (5-Minute Candles)

**Purpose:** Store 5-minute OHLCV candles for all tickers  
**Type:** TimescaleDB Hypertable  
**Retention:** KEEP FOREVER (no drop policy)  
**Compression:** Enabled for chunks >24 hours

| Column Name | Type | Constraints | Description |
|------------|------|-------------|-------------|
| `ticker` | VARCHAR(10) | PRIMARY KEY, NOT NULL | Stock symbol |
| `time` | TIMESTAMPTZ | PRIMARY KEY, NOT NULL | Timestamp (5-minute resolution) |
| `open` | DOUBLE PRECISION | NOT NULL | Opening price |
| `high` | DOUBLE PRECISION | NOT NULL | High price |
| `low` | DOUBLE PRECISION | NOT NULL | Low price |
| `close` | DOUBLE PRECISION | NOT NULL | Closing price |
| `volume` | BIGINT | NOT NULL | Volume |
| `vwap` | DOUBLE PRECISION | NULL | Volume-weighted average price |
| `source` | VARCHAR(32) | NOT NULL DEFAULT 'unknown' | Data source provider |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Record creation timestamp |

**Indexes:**
- Primary key: `(ticker, time)` (composite, ticker first for query optimization)
- Index on `time` for time-range queries

---

### 3. `candles_1d` (Daily Candles)

**Purpose:** Store daily OHLCV candles for all tickers  
**Type:** TimescaleDB Hypertable  
**Retention:** KEEP FOREVER (no drop policy)  
**Compression:** Enabled for chunks >24 hours

| Column Name | Type | Constraints | Description |
|------------|------|-------------|-------------|
| `ticker` | VARCHAR(10) | PRIMARY KEY, NOT NULL | Stock symbol |
| `time` | TIMESTAMPTZ | PRIMARY KEY, NOT NULL | Trading date (normalized to 00:00:00Z per trading day) |
| `open` | DOUBLE PRECISION | NOT NULL | Opening price |
| `high` | DOUBLE PRECISION | NOT NULL | High price |
| `low` | DOUBLE PRECISION | NOT NULL | Low price |
| `close` | DOUBLE PRECISION | NOT NULL | Closing price |
| `volume` | BIGINT | NOT NULL | Volume |
| `vwap` | DOUBLE PRECISION | NULL | Volume-weighted average price |
| `source` | VARCHAR(32) | NOT NULL DEFAULT 'unknown' | Data source provider |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Record creation timestamp |

**Indexes:**
- Primary key: `(ticker, time)` (composite, ticker first for query optimization)
- Index on `time` for time-range queries

---

### 4. `ticks` (High-Frequency Tick Data)

**Purpose:** Store tick-level data for H30 model and debugging  
**Type:** TimescaleDB Hypertable  
**Retention:** DROP chunks older than 7 days  
**Compression:** Disabled (too high frequency)

| Column Name | Type | Constraints | Description |
|------------|------|-------------|-------------|
| `ticker` | VARCHAR(10) | PRIMARY KEY, NOT NULL | Stock symbol |
| `time` | TIMESTAMPTZ | PRIMARY KEY, NOT NULL | Timestamp (microsecond resolution from feed) |
| `ingest_seq` | BIGSERIAL | PRIMARY KEY, NOT NULL | Auto-incrementing ID for collision prevention |
| `price` | DOUBLE PRECISION | NOT NULL | Last trade price |
| `volume` | BIGINT | NOT NULL | Trade volume |
| `bid` | DOUBLE PRECISION | NULL | Best bid price |
| `ask` | DOUBLE PRECISION | NULL | Best ask price |
| `spread` | DOUBLE PRECISION | NULL | Ask - Bid spread |
| `source` | VARCHAR(32) | NOT NULL DEFAULT 'unknown' | Data source provider |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Record creation timestamp |

**Indexes:**
- Primary key: `(ticker, time, ingest_seq)` (includes ingest_seq to prevent collisions when multiple ticks share same timestamp)
- Index on `time` for time-range queries

---

### 5. `regime_log` (Market Regime History)

**Purpose:** Log market permission states (Level 0)  
**Type:** TimescaleDB Hypertable (recommended)  
**Retention:** KEEP FOREVER

| Column Name | Type | Constraints | Description |
|------------|------|-------------|-------------|
| `id` | BIGSERIAL | PRIMARY KEY | Auto-increment ID |
| `time` | TIMESTAMPTZ | NOT NULL, INDEX | Timestamp |
| `state` | VARCHAR(10) | NOT NULL | GREEN, YELLOW, or RED |
| `vix_level` | NUMERIC(8,4) | NULL | VIX level |
| `vix_roc` | NUMERIC(8,4) | NULL | VIX rate of change |
| `adv_decl` | NUMERIC(12,4) | NULL | Advance/Decline ratio |
| `trin` | NUMERIC(8,4) | NULL | TRIN (Trading Index) |
| `breadth_score` | NUMERIC(8,4) | NULL | Market breadth score |
| `event_risk` | BOOLEAN | DEFAULT FALSE | Event risk flag |
| `reason` | TEXT | NULL | Human-readable reason for state |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Record creation timestamp |

**Indexes:**
- Primary key: `id`
- Index on `time` for time-range queries
- Index on `state` for state-based queries

---

### 6. `ingest_gap_log` (Gap Detection & Backfill Tracking)

**Purpose:** Track data gaps and backfill attempts  
**Type:** Regular PostgreSQL table  
**Retention:** KEEP FOREVER

| Column Name | Type | Constraints | Description |
|------------|------|-------------|-------------|
| `id` | BIGSERIAL | PRIMARY KEY | Auto-increment ID |
| `ticker` | VARCHAR(10) | NOT NULL, INDEX | Stock symbol |
| `timeframe` | VARCHAR(10) | NOT NULL | 1m, 5m, 1d, or tick |
| `gap_start` | TIMESTAMPTZ | NOT NULL | Start of gap |
| `gap_end` | TIMESTAMPTZ | NOT NULL | End of gap |
| `detection_time` | TIMESTAMPTZ | NOT NULL | When gap was detected |
| `backfilled` | BOOLEAN | DEFAULT FALSE | Whether gap was backfilled |
| `backfill_time` | TIMESTAMPTZ | NULL | When backfill was attempted |
| `backfill_success` | BOOLEAN | NULL | Whether backfill succeeded |
| `reason` | TEXT | NULL | Reason for gap (feed outage, etc.) |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Record creation timestamp |

**Indexes:**
- Primary key: `id`
- Index on `ticker` for ticker-specific queries
- Index on `timeframe` for timeframe-based queries
- Index on `(ticker, timeframe, gap_start)` for gap queries
- Index on `backfilled` for backfill tracking

---

### 7. `attention_log` (Attention State History)

**Purpose:** Log attention states (Level 1)  
**Type:** TimescaleDB Hypertable (recommended)  
**Retention:** KEEP FOREVER

| Column Name | Type | Constraints | Description |
|------------|------|-------------|-------------|
| `id` | BIGSERIAL | PRIMARY KEY | Auto-increment ID |
| `time` | TIMESTAMPTZ | NOT NULL, INDEX | Timestamp |
| `dominant_sectors` | JSONB | NULL | Array of dominant sectors with scores |
| `attention_concentration` | NUMERIC(5,2) | NULL | 0-100 score |
| `attention_stability` | NUMERIC(5,2) | NULL | 0-100 score (half-life proxy) |
| `risk_on_off_state` | VARCHAR(10) | NULL | RISK_ON, RISK_OFF, or NEUTRAL |
| `correlation_regime` | VARCHAR(20) | NULL | Correlation regime description |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Record creation timestamp |

**Indexes:**
- Primary key: `id`
- Index on `time` for time-range queries
- Index on `attention_stability` for stability queries

---

### 8. `opportunity_log` (Opportunity History)

**Purpose:** Log all opportunities generated (Level 3)  
**Type:** Regular PostgreSQL table  
**Retention:** KEEP FOREVER

| Column Name | Type | Constraints | Description |
|------------|------|-------------|-------------|
| `id` | BIGSERIAL | PRIMARY KEY | Auto-increment ID |
| `time` | TIMESTAMPTZ | NOT NULL, INDEX | Timestamp when opportunity was issued |
| `ticker` | VARCHAR(10) | NOT NULL, INDEX | Stock symbol |
| `horizon` | VARCHAR(10) | NOT NULL | H30, H2H, HDAY, or HWEEK |
| `opportunity_score` | NUMERIC(5,2) | NOT NULL | 0-100 score |
| `probability` | NUMERIC(5,4) | NOT NULL | Probability (0.0000-1.0000) |
| `target_atr` | NUMERIC(8,4) | NOT NULL | Target excursion in ATR |
| `stop_atr` | NUMERIC(8,4) | NOT NULL | Stop excursion in ATR |
| `market_state` | VARCHAR(10) | NOT NULL | GREEN, YELLOW, or RED |
| `attention_stability_score` | NUMERIC(5,2) | NOT NULL | 0-100 stability score (score-based, not discrete state) |
| `attention_bucket` | VARCHAR(10) | NULL | Derived bucket: STABLE (>=70), UNSTABLE (40-69), CHAOTIC (<40) - for convenience only |
| `attention_alignment` | NUMERIC(5,2) | NULL | 0-100 alignment score |
| `regime_dependency` | JSONB | NULL | Required market states |
| `key_levels` | JSONB | NULL | VWAP, support, resistance levels |
| `invalidation_rule` | TEXT | NULL | Invalidation conditions |
| `why` | JSONB | NULL | Explanation list |
| `liquidity_grade` | VARCHAR(10) | NULL | Liquidity assessment |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Record creation timestamp |

**Indexes:**
- Primary key: `id`
- Index on `time` for time-range queries
- Index on `ticker` for ticker-specific queries
- Index on `horizon` for horizon-based queries
- Index on `(time, ticker, horizon)` for performance queries
- Index on `opportunity_score` for ranking queries

---

### 9. `performance_log` (Truth Test Results)

**Purpose:** Store truth test outcomes (MFE/MAE results)  
**Type:** Regular PostgreSQL table  
**Retention:** KEEP FOREVER

| Column Name | Type | Constraints | Description |
|------------|------|-------------|-------------|
| `id` | BIGSERIAL | PRIMARY KEY | Auto-increment ID |
| `opportunity_id` | BIGINT | NOT NULL, INDEX, FOREIGN KEY | Reference to opportunity_log.id |
| `ticker` | VARCHAR(10) | NOT NULL, INDEX | Stock symbol |
| `horizon` | VARCHAR(10) | NOT NULL | H30, H2H, HDAY, or HWEEK |
| `issued_time` | TIMESTAMPTZ | NOT NULL | When opportunity was issued |
| `regime_state` | VARCHAR(10) | NOT NULL | Market state at issue time |
| `attention_stability_score` | NUMERIC(5,2) | NOT NULL | Attention stability score (0-100) at issue time |
| `attention_bucket` | VARCHAR(10) | NULL | Derived bucket: STABLE/UNSTABLE/CHAOTIC (for convenience only) |
| `mfe_atr` | NUMERIC(8,4) | NULL | Realized Max Favorable Excursion (ATR) |
| `mae_atr` | NUMERIC(8,4) | NULL | Realized Max Adverse Excursion (ATR) |
| `outcome` | VARCHAR(10) | NOT NULL | PASS, FAIL, or NEUTRAL |
| `target_hit_first` | BOOLEAN | NULL | True if MFE >= target before MAE >= stop |
| `stop_hit_first` | BOOLEAN | NULL | True if MAE >= stop before MFE >= target |
| `neither_hit` | BOOLEAN | NULL | True if neither target nor stop hit |
| `evaluation_time` | TIMESTAMPTZ | NOT NULL | When truth test was run |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | Record creation timestamp |

**Indexes:**
- Primary key: `id`
- Foreign key: `opportunity_id` → `opportunity_log.id`
- Index on `ticker` for ticker-specific queries
- Index on `horizon` for horizon-based queries
- Index on `outcome` for outcome analysis
- Index on `(regime_state, attention_stability_score, horizon)` for calibration queries

---

## TIMESCALEDB CONFIGURATION

### Hypertables

The following tables are converted to TimescaleDB hypertables:
- `candles_1m` (partitioned by `time`)
- `candles_5m` (partitioned by `time`)
- `candles_1d` (partitioned by `time`)
- `ticks` (partitioned by `time`)
- `regime_log` (partitioned by `time`) - recommended
- `attention_log` (partitioned by `time`) - recommended

### Compression

Compression is enabled for:
- `candles_1m` (chunks older than 24 hours)
- `candles_5m` (chunks older than 24 hours)
- `candles_1d` (chunks older than 24 hours)

Compression is **NOT** enabled for:
- `ticks` (too high frequency, not beneficial)

### Retention Policies

| Table | Policy | Description |
|-------|--------|-------------|
| `ticks` | DROP chunks older than 7 days | High-frequency data, only needed for H30 |
| `candles_1m` | DROP chunks older than 1 year | Used for backtesting intraday models |
| `candles_5m` | KEEP FOREVER | No drop policy |
| `candles_1d` | KEEP FOREVER | No drop policy |

---

## DATABASE CONNECTION

**Inside Docker containers:**
- **Host:** `timescaledb` (Docker service name)
- **Port:** 5432
- **Database:** `zero_trading`
- **User:** `zero_user`
- **Password:** From environment variable `POSTGRES_PASSWORD`

**From host machine (if ports published):**
- **Host:** `localhost`
- **Port:** 5432

---

## MIGRATION NOTES

### Schema Versioning

All schema changes require:
1. Update `db_schema.md` version
2. Create migration script in `/infra/db/migrations/`
3. Update `init.sql` if needed
4. Document breaking changes

### Breaking Changes

Breaking changes require:
- Major version bump
- Migration script
- Backward compatibility consideration

---

**END OF DATABASE SCHEMA CONTRACT**

