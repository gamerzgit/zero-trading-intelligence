-- Migration: Add execution_log table (Milestone 6)
-- Run this if execution_log table doesn't exist

CREATE TABLE IF NOT EXISTS execution_log (
    id BIGSERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    execution_id TEXT NOT NULL UNIQUE,  -- Idempotency key
    ticker VARCHAR(10) NOT NULL,
    horizon VARCHAR(10) NOT NULL,  -- H30, H2H, HDAY, or HWEEK
    probability NUMERIC(5,4),  -- From opportunity
    opportunity_score NUMERIC(5,2),  -- From opportunity
    status VARCHAR(20) NOT NULL,  -- SUBMITTED, BLOCKED, SKIPPED, REJECTED, ERROR
    alpaca_order_id TEXT,  -- Alpaca order ID if submitted
    why JSONB,  -- Array of reason strings
    market_state_snapshot JSONB,  -- Market state at execution time
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_execution_log_time ON execution_log (time);
CREATE INDEX IF NOT EXISTS idx_execution_log_execution_id ON execution_log (execution_id);
CREATE INDEX IF NOT EXISTS idx_execution_log_ticker ON execution_log (ticker);
CREATE INDEX IF NOT EXISTS idx_execution_log_status ON execution_log (status);
CREATE INDEX IF NOT EXISTS idx_execution_log_time_ticker ON execution_log (time, ticker);
