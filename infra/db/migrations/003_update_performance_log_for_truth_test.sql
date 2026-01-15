-- Migration: Update performance_log for Truth Test (Milestone 7)
-- Adds fields required for MFE/MAE tracking and calibration

-- Add new columns if they don't exist
ALTER TABLE performance_log ADD COLUMN IF NOT EXISTS probability_issued NUMERIC(5,4);
ALTER TABLE performance_log ADD COLUMN IF NOT EXISTS target_atr NUMERIC(8,4);
ALTER TABLE performance_log ADD COLUMN IF NOT EXISTS stop_atr NUMERIC(8,4);
ALTER TABLE performance_log ADD COLUMN IF NOT EXISTS atr_value NUMERIC(8,4);
ALTER TABLE performance_log ADD COLUMN IF NOT EXISTS entry_price NUMERIC(12,4);
ALTER TABLE performance_log ADD COLUMN IF NOT EXISTS realized_mfe NUMERIC(12,4);
ALTER TABLE performance_log ADD COLUMN IF NOT EXISTS realized_mae NUMERIC(12,4);
ALTER TABLE performance_log ADD COLUMN IF NOT EXISTS debug_json JSONB;

-- Update outcome to include NO_DATA and EXPIRED
-- outcome VARCHAR(10) already exists, just document the new values:
-- PASS, FAIL, EXPIRED, NO_DATA

COMMENT ON COLUMN performance_log.probability_issued IS 'Probability at time of opportunity issuance';
COMMENT ON COLUMN performance_log.target_atr IS 'Target excursion in ATR units';
COMMENT ON COLUMN performance_log.stop_atr IS 'Stop excursion in ATR units';
COMMENT ON COLUMN performance_log.atr_value IS 'ATR value at issue time (for converting to absolute prices)';
COMMENT ON COLUMN performance_log.entry_price IS 'Entry reference price (1m candle close at issue time)';
COMMENT ON COLUMN performance_log.realized_mfe IS 'Realized Max Favorable Excursion (absolute price)';
COMMENT ON COLUMN performance_log.realized_mae IS 'Realized Max Adverse Excursion (absolute price)';
COMMENT ON COLUMN performance_log.debug_json IS 'Debug information (candle counts, timestamps, etc.)';
