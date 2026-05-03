ALTER TABLE jobs
ADD COLUMN closure_service_type VARCHAR(32) NULL AFTER closure_status;