-- Migration: Add realized_outcome and time_to_resolution to performance_log
-- Per Milestone 7 spec requirements

-- realized_outcome: BOOLEAN - True=SUCCESS (MFE >= target before MAE >= stop), False=FAILURE
ALTER TABLE performance_log ADD COLUMN IF NOT EXISTS realized_outcome BOOLEAN;

-- time_to_resolution: Seconds from issue_time to when target or stop was hit
ALTER TABLE performance_log ADD COLUMN IF NOT EXISTS time_to_resolution DOUBLE PRECISION;

-- Add index for calibration queries on realized_outcome
CREATE INDEX IF NOT EXISTS idx_performance_log_realized_outcome ON performance_log (realized_outcome);

COMMENT ON COLUMN performance_log.realized_outcome IS 'True if MFE >= target_atr before MAE >= stop_atr (SUCCESS), False otherwise (FAILURE)';
COMMENT ON COLUMN performance_log.time_to_resolution IS 'Seconds from issue_time to resolution (target or stop hit)';
