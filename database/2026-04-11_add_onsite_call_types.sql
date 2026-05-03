ALTER TABLE onsite_calls
    ADD COLUMN call_type VARCHAR(20) NOT NULL DEFAULT 'Onsite',
    ADD COLUMN lead_source VARCHAR(255) NULL;

UPDATE onsite_calls
SET call_type = 'Onsite'
WHERE call_type IS NULL OR TRIM(call_type) = '';

CREATE INDEX idx_onsite_calls_call_type ON onsite_calls (call_type);
