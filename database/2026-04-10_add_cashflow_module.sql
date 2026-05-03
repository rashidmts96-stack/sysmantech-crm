CREATE TABLE IF NOT EXISTS branch_cashflow_entries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    entry_date DATE NOT NULL,
    branch_name VARCHAR(255) NOT NULL,
    cash_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    card_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    upi_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    total_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    remarks VARCHAR(255) NULL,
    created_by VARCHAR(255) NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_cashflow_entry_date_branch (entry_date, branch_name),
    INDEX idx_cashflow_entry_date (entry_date),
    INDEX idx_cashflow_entry_branch (branch_name)
);

CREATE TABLE IF NOT EXISTS branch_cash_transfer_requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    branch_name VARCHAR(255) NOT NULL,
    request_date DATE NOT NULL,
    amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    transfer_to VARCHAR(255) NULL,
    requested_notes TEXT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Pending',
    requested_by VARCHAR(255) NULL,
    requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    reviewed_by VARCHAR(255) NULL,
    reviewed_at DATETIME NULL,
    review_notes TEXT NULL,
    transfer_reference VARCHAR(120) NULL,
    INDEX idx_cash_transfer_branch_status (branch_name, status),
    INDEX idx_cash_transfer_request_date (request_date)
);