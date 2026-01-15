-- Migration: Add calibration_log table (Milestone 7)
-- Persists calibration snapshots for audit and recovery

CREATE TABLE IF NOT EXISTS calibration_log (
    id BIGSERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    buckets_json JSONB NOT NULL,
    global_stats_json JSONB NOT NULL,
    degraded_horizons TEXT[] DEFAULT '{}',
    degraded_states TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_calibration_log_time ON calibration_log (time);

COMMENT ON TABLE calibration_log IS 'Persisted calibration snapshots from truth-test service';
COMMENT ON COLUMN calibration_log.buckets_json IS 'Per-bucket calibration metrics and shrink factors';
COMMENT ON COLUMN calibration_log.global_stats_json IS 'Global calibration statistics';
COMMENT ON COLUMN calibration_log.degraded_horizons IS 'List of horizons with shrink_factor < 1.0';
COMMENT ON COLUMN calibration_log.degraded_states IS 'List of market states with shrink_factor < 1.0';
