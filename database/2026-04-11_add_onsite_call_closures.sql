CREATE TABLE IF NOT EXISTS onsite_call_closures (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    call_id INT NOT NULL,
    final_status VARCHAR(50) NOT NULL,
    close_reason TEXT NULL,
    completion_type VARCHAR(32) NULL,
    narration TEXT NULL,
    service_charges DECIMAL(12,2) NOT NULL DEFAULT 0,
    engineer_id INT NULL,
    product_value DECIMAL(12,2) NOT NULL DEFAULT 0,
    customer_price DECIMAL(12,2) NOT NULL DEFAULT 0,
    closed_by_brand VARCHAR(32) NULL,
    payment_mode VARCHAR(16) NULL,
    payment_status VARCHAR(32) NULL,
    closed_by_user VARCHAR(255) NULL,
    closed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_onsite_call_closures_call
        FOREIGN KEY (call_id) REFERENCES onsite_calls(id)
        ON DELETE CASCADE,
    UNIQUE KEY uq_onsite_call_closures_call_id (call_id),
    KEY idx_onsite_call_closures_payment_status (payment_status)
);