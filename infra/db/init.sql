-- ZERO Trading Intelligence Platform - Database Initialization Script
-- Version: 1.0
-- Last Updated: 2026-01-11
-- Database: TimescaleDB (PostgreSQL extension)

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================================================
-- 1. CANDLES TABLES (Hypertables)
-- ============================================================================

-- 1-minute candles
CREATE TABLE candles_1m (
    ticker VARCHAR(10) NOT NULL,
    time TIMESTAMPTZ NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume BIGINT NOT NULL,
    vwap DOUBLE PRECISION,
    source VARCHAR(32) NOT NULL DEFAULT 'unknown',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (ticker, time)
);

CREATE INDEX idx_candles_1m_time ON candles_1m (time);

-- Convert to hypertable
SELECT create_hypertable('candles_1m', 'time', chunk_time_interval => INTERVAL '1 day');

-- Enable compression for chunks older than 24 hours
ALTER TABLE candles_1m SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'ticker',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('candles_1m', INTERVAL '24 hours');

-- Retention policy: DROP chunks older than 1 year
SELECT add_retention_policy('candles_1m', INTERVAL '1 year');

-- 5-minute candles
CREATE TABLE candles_5m (
    ticker VARCHAR(10) NOT NULL,
    time TIMESTAMPTZ NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume BIGINT NOT NULL,
    vwap DOUBLE PRECISION,
    source VARCHAR(32) NOT NULL DEFAULT 'unknown',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (ticker, time)
);

CREATE INDEX idx_candles_5m_time ON candles_5m (time);

-- Convert to hypertable
SELECT create_hypertable('candles_5m', 'time', chunk_time_interval => INTERVAL '7 days');

-- Enable compression for chunks older than 24 hours
ALTER TABLE candles_5m SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'ticker',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('candles_5m', INTERVAL '24 hours');

-- Retention: KEEP FOREVER (no drop policy)

-- Daily candles
CREATE TABLE candles_1d (
    ticker VARCHAR(10) NOT NULL,
    time TIMESTAMPTZ NOT NULL,  -- TIMESTAMPTZ, not DATE (normalized to 00:00:00Z per trading day)
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume BIGINT NOT NULL,
    vwap DOUBLE PRECISION,
    source VARCHAR(32) NOT NULL DEFAULT 'unknown',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (ticker, time)
);

CREATE INDEX idx_candles_1d_time ON candles_1d (time);

-- Convert to hypertable
SELECT create_hypertable('candles_1d', 'time', chunk_time_interval => INTERVAL '30 days');

-- Enable compression for chunks older than 24 hours
ALTER TABLE candles_1d SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'ticker',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('candles_1d', INTERVAL '24 hours');

-- Retention: KEEP FOREVER (no drop policy)

-- ============================================================================
-- 2. TICKS TABLE (Hypertable)
-- ============================================================================

CREATE TABLE ticks (
    ticker VARCHAR(10) NOT NULL,
    time TIMESTAMPTZ NOT NULL,  -- Microsecond resolution from feed
    price DOUBLE PRECISION NOT NULL,
    volume BIGINT NOT NULL,
    bid DOUBLE PRECISION,
    ask DOUBLE PRECISION,
    spread DOUBLE PRECISION,
    source VARCHAR(32) NOT NULL DEFAULT 'unknown',
    ingest_seq BIGSERIAL NOT NULL,  -- Auto-incrementing ID for collision prevention
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (ticker, time, ingest_seq)  -- Includes ingest_seq to prevent collisions
);

CREATE INDEX idx_ticks_time ON ticks (time);

-- Convert to hypertable
SELECT create_hypertable('ticks', 'time', chunk_time_interval => INTERVAL '1 hour');

-- Compression: NOT enabled (too high frequency, not beneficial)

-- Retention policy: DROP chunks older than 7 days
SELECT add_retention_policy('ticks', INTERVAL '7 days');

-- ============================================================================
-- 3. REGIME LOG (Hypertable - Recommended)
-- ============================================================================

CREATE TABLE regime_log (
    id BIGSERIAL,
    time TIMESTAMPTZ NOT NULL,
    state VARCHAR(10) NOT NULL,  -- GREEN, YELLOW, or RED
    vix_level DOUBLE PRECISION,
    vix_roc DOUBLE PRECISION,
    adv_decl DOUBLE PRECISION,
    trin DOUBLE PRECISION,
    breadth_score DOUBLE PRECISION,
    event_risk BOOLEAN DEFAULT FALSE,
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (id, time)
);

CREATE INDEX idx_regime_log_time ON regime_log (time);
CREATE INDEX idx_regime_log_state ON regime_log (state);

-- Convert to hypertable
SELECT create_hypertable('regime_log', 'time', chunk_time_interval => INTERVAL '7 days');

-- ============================================================================
-- 4. ATTENTION LOG (Hypertable - Recommended)
-- ============================================================================

CREATE TABLE attention_log (
    id BIGSERIAL,
    time TIMESTAMPTZ NOT NULL,
    dominant_sectors JSONB,
    attention_concentration NUMERIC(5,2),  -- 0-100 score
    attention_stability NUMERIC(5,2),     -- 0-100 score (half-life proxy)
    risk_on_off_state VARCHAR(10),         -- RISK_ON, RISK_OFF, or NEUTRAL
    correlation_regime VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (id, time)
);

CREATE INDEX idx_attention_log_time ON attention_log (time);
CREATE INDEX idx_attention_log_stability ON attention_log (attention_stability);

-- Convert to hypertable
SELECT create_hypertable('attention_log', 'time', chunk_time_interval => INTERVAL '7 days');

-- ============================================================================
-- 5. GAP LOG (Gap Detection & Backfill Tracking)
-- ============================================================================

CREATE TABLE ingest_gap_log (
    id BIGSERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,  -- 1m, 5m, 1d, or tick
    gap_start TIMESTAMPTZ NOT NULL,
    gap_end TIMESTAMPTZ NOT NULL,
    detection_time TIMESTAMPTZ NOT NULL,
    backfilled BOOLEAN DEFAULT FALSE,
    backfill_time TIMESTAMPTZ,
    backfill_success BOOLEAN,
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_gap_log_ticker ON ingest_gap_log (ticker);
CREATE INDEX idx_gap_log_timeframe ON ingest_gap_log (timeframe);
CREATE INDEX idx_gap_log_ticker_timeframe_start ON ingest_gap_log (ticker, timeframe, gap_start);
CREATE INDEX idx_gap_log_backfilled ON ingest_gap_log (backfilled);

-- ============================================================================
-- 6. OPPORTUNITY LOG
-- ============================================================================

CREATE TABLE opportunity_log (
    id BIGSERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    horizon VARCHAR(10) NOT NULL,  -- H30, H2H, HDAY, or HWEEK
    opportunity_score NUMERIC(5,2) NOT NULL,  -- 0-100 score
    probability NUMERIC(5,4) NOT NULL,  -- 0.0000-1.0000
    target_atr NUMERIC(8,4) NOT NULL,
    stop_atr NUMERIC(8,4) NOT NULL,
    market_state VARCHAR(10) NOT NULL,  -- GREEN, YELLOW, or RED
    attention_stability_score NUMERIC(5,2) NOT NULL,  -- 0-100 (score-based, not discrete state)
    attention_bucket VARCHAR(10),  -- Derived: STABLE (>=70), UNSTABLE (40-69), CHAOTIC (<40)
    attention_alignment NUMERIC(5,2),
    regime_dependency JSONB,
    key_levels JSONB,
    invalidation_rule TEXT,
    why JSONB,
    liquidity_grade VARCHAR(10),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_opportunity_log_time ON opportunity_log (time);
CREATE INDEX idx_opportunity_log_ticker ON opportunity_log (ticker);
CREATE INDEX idx_opportunity_log_horizon ON opportunity_log (horizon);
CREATE INDEX idx_opportunity_log_time_ticker_horizon ON opportunity_log (time, ticker, horizon);
CREATE INDEX idx_opportunity_log_score ON opportunity_log (opportunity_score);

-- ============================================================================
-- 7. PERFORMANCE LOG (Truth Test Results)
-- ============================================================================

CREATE TABLE performance_log (
    id BIGSERIAL PRIMARY KEY,
    opportunity_id BIGINT NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    horizon VARCHAR(10) NOT NULL,  -- H30, H2H, HDAY, or HWEEK
    issued_time TIMESTAMPTZ NOT NULL,
    regime_state VARCHAR(10) NOT NULL,  -- Market state at issue time
    attention_stability_score NUMERIC(5,2) NOT NULL,  -- 0-100 (score-based, not discrete state)
    attention_bucket VARCHAR(10),  -- Derived: STABLE/UNSTABLE/CHAOTIC (for convenience only)
    mfe_atr NUMERIC(8,4),  -- Realized Max Favorable Excursion (ATR)
    mae_atr NUMERIC(8,4),  -- Realized Max Adverse Excursion (ATR)
    outcome VARCHAR(10) NOT NULL,  -- PASS, FAIL, or NEUTRAL
    target_hit_first BOOLEAN,  -- True if MFE >= target before MAE >= stop
    stop_hit_first BOOLEAN,    -- True if MAE >= stop before MFE >= target
    neither_hit BOOLEAN,        -- True if neither target nor stop hit
    evaluation_time TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (opportunity_id) REFERENCES opportunity_log(id)
);

CREATE INDEX idx_performance_log_opportunity_id ON performance_log (opportunity_id);
CREATE INDEX idx_performance_log_ticker ON performance_log (ticker);
CREATE INDEX idx_performance_log_horizon ON performance_log (horizon);
CREATE INDEX idx_performance_log_outcome ON performance_log (outcome);
CREATE INDEX idx_performance_log_calibration ON performance_log (regime_state, attention_stability_score, horizon);

-- ============================================================================
-- END OF INITIALIZATION
-- ============================================================================

-- Verify TimescaleDB extension
SELECT * FROM timescaledb_information.hypertables;

-- Display retention policies
SELECT * FROM timescaledb_information.jobs WHERE proc_name LIKE '%retention%';

-- Display compression policies
SELECT * FROM timescaledb_information.jobs WHERE proc_name LIKE '%compression%';

