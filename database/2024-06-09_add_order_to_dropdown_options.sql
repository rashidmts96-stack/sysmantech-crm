-- Migration: Add 'order' column to dropdown_options
ALTER TABLE dropdown_options ADD COLUMN `order` INT NOT NULL DEFAULT 0;

-- Optional: Initialize order values for existing rows (by id)
SET @rownum = 0;
UPDATE dropdown_options SET `order` = (@rownum := @rownum + 1) ORDER BY type, value, id;

-- Add index for faster ordering queries
CREATE INDEX idx_dropdown_options_order ON dropdown_options(type, `order`);