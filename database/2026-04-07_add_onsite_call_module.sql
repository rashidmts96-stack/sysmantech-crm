CREATE TABLE IF NOT EXISTS onsite_calls (
    id INT NOT NULL AUTO_INCREMENT,
    customer_name VARCHAR(255) NOT NULL,
    phone VARCHAR(50) NOT NULL,
    location VARCHAR(255) NOT NULL,
    district VARCHAR(255) NOT NULL,
    complaint_type VARCHAR(50) NOT NULL,
    preferred_service VARCHAR(50) NOT NULL,
    priority VARCHAR(50) NOT NULL,
    preferred_datetime DATETIME NOT NULL,
    device_model VARCHAR(255) NULL,
    complaint_description TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'New Lead',
    source VARCHAR(50) NOT NULL,
    assigned_branch_id INT NULL,
    assigned_engineer_id INT NULL,
    assigned_time DATETIME NULL,
    created_by VARCHAR(255) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_onsite_calls_status (status),
    KEY idx_onsite_calls_branch (assigned_branch_id),
    KEY idx_onsite_calls_engineer (assigned_engineer_id),
    KEY idx_onsite_calls_created_at (created_at),
    KEY idx_onsite_calls_status_created (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS onsite_call_logs (
    id INT NOT NULL AUTO_INCREMENT,
    call_id INT NOT NULL,
    action VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    done_by VARCHAR(255) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_onsite_call_logs_call_id (call_id),
    CONSTRAINT fk_onsite_call_logs_call_id
        FOREIGN KEY (call_id) REFERENCES onsite_calls(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS onsite_call_notes (
    id INT NOT NULL AUTO_INCREMENT,
    call_id INT NOT NULL,
    note TEXT NOT NULL,
    created_by VARCHAR(255) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_onsite_call_notes_call_id (call_id),
    CONSTRAINT fk_onsite_call_notes_call_id
        FOREIGN KEY (call_id) REFERENCES onsite_calls(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
