-- Migration: 001_allow_null_from_location
-- Purpose: Allow inventory movements originating outside the warehouse,
--          such as customer returns, to have a NULL from_location.

ALTER TABLE prism_data.movements
ALTER COLUMN from_location DROP NOT NULL;
