SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS=0;

-- Table: branch_cash_transfer_requests
CREATE TABLE `branch_cash_transfer_requests` (
  `id` int NOT NULL AUTO_INCREMENT,
  `branch_name` varchar(255) NOT NULL,
  `request_date` date NOT NULL,
  `amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `transfer_to` varchar(255) DEFAULT NULL,
  `requested_notes` text,
  `status` varchar(20) NOT NULL DEFAULT 'Pending',
  `requested_by` varchar(255) DEFAULT NULL,
  `requested_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `reviewed_by` varchar(255) DEFAULT NULL,
  `reviewed_at` datetime DEFAULT NULL,
  `review_notes` text,
  `transfer_reference` varchar(120) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_cash_transfer_branch_status` (`branch_name`,`status`),
  KEY `idx_cash_transfer_request_date` (`request_date`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: branch_cashflow_entries
CREATE TABLE `branch_cashflow_entries` (
  `id` int NOT NULL AUTO_INCREMENT,
  `entry_date` date NOT NULL,
  `branch_name` varchar(255) NOT NULL,
  `cash_amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `card_amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `upi_amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `total_amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `remarks` varchar(255) DEFAULT NULL,
  `created_by` varchar(255) DEFAULT NULL,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_cashflow_entry_date_branch` (`entry_date`,`branch_name`),
  KEY `idx_cashflow_entry_date` (`entry_date`),
  KEY `idx_cashflow_entry_branch` (`branch_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: branch_chat_messages
CREATE TABLE `branch_chat_messages` (
  `id` int NOT NULL AUTO_INCREMENT,
  `target_branch_name` varchar(255) NOT NULL,
  `sender_username` varchar(255) NOT NULL,
  `sender_role` varchar(100) NOT NULL,
  `message_text` text,
  `attachment_stored_name` varchar(255) DEFAULT NULL,
  `attachment_original_name` varchar(255) DEFAULT NULL,
  `attachment_mime_type` varchar(255) DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_branch_chat_room_created` (`target_branch_name`,`created_at`),
  KEY `idx_branch_chat_created` (`created_at`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: branch_print_profiles
CREATE TABLE `branch_print_profiles` (
  `id` int NOT NULL AUTO_INCREMENT,
  `branch_name` varchar(255) NOT NULL,
  `company_name` varchar(255) NOT NULL DEFAULT 'SYSMANTECH',
  `address_line1` varchar(255) DEFAULT NULL,
  `address_line2` varchar(255) DEFAULT NULL,
  `gst_no` varchar(100) DEFAULT NULL,
  `mobile1` varchar(50) DEFAULT NULL,
  `mobile2` varchar(50) DEFAULT NULL,
  `mobile3` varchar(50) DEFAULT NULL,
  `terms_text` text,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `quotation_terms` text,
  PRIMARY KEY (`id`),
  UNIQUE KEY `branch_name` (`branch_name`)
) ENGINE=InnoDB AUTO_INCREMENT=33 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: branch_profit_reports
CREATE TABLE `branch_profit_reports` (
  `id` int NOT NULL AUTO_INCREMENT,
  `from_date` date NOT NULL,
  `to_date` date NOT NULL,
  `branch_name` varchar(255) NOT NULL,
  `total_profit` decimal(12,2) NOT NULL DEFAULT '0.00',
  `uploaded_by` varchar(255) DEFAULT NULL,
  `uploaded_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_profit_report_period_branch` (`from_date`,`to_date`,`branch_name`),
  KEY `idx_profit_report_period` (`from_date`,`to_date`),
  KEY `idx_profit_report_branch` (`branch_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: branch_revenue_entries
CREATE TABLE `branch_revenue_entries` (
  `id` int NOT NULL AUTO_INCREMENT,
  `entry_date` date NOT NULL,
  `branch_name` varchar(255) NOT NULL,
  `sales_profit` decimal(12,2) NOT NULL DEFAULT '0.00',
  `service_charges` decimal(12,2) NOT NULL DEFAULT '0.00',
  `total_profit` decimal(12,2) NOT NULL DEFAULT '0.00',
  `zone` varchar(100) DEFAULT NULL,
  `created_by` varchar(255) DEFAULT NULL,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_revenue_entry_date_branch` (`entry_date`,`branch_name`),
  KEY `idx_revenue_entry_date` (`entry_date`),
  KEY `idx_revenue_branch` (`branch_name`),
  KEY `idx_revenue_entry_branch_date` (`branch_name`,`entry_date`)
) ENGINE=InnoDB AUTO_INCREMENT=93 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: branch_revenue_report_snapshots
CREATE TABLE `branch_revenue_report_snapshots` (
  `id` int NOT NULL AUTO_INCREMENT,
  `from_date` date NOT NULL,
  `to_date` date NOT NULL,
  `branch_name` varchar(255) NOT NULL,
  `total_revenue` decimal(12,2) NOT NULL DEFAULT '0.00',
  `uploaded_by` varchar(255) DEFAULT NULL,
  `uploaded_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_revenue_snapshot_period_branch` (`from_date`,`to_date`,`branch_name`),
  KEY `idx_revenue_snapshot_period` (`from_date`,`to_date`),
  KEY `idx_revenue_snapshot_branch` (`branch_name`)
) ENGINE=InnoDB AUTO_INCREMENT=91 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: branch_revenue_targets
CREATE TABLE `branch_revenue_targets` (
  `id` int NOT NULL AUTO_INCREMENT,
  `branch_name` varchar(255) NOT NULL,
  `sales_target` decimal(12,2) NOT NULL DEFAULT '0.00',
  `service_target` decimal(12,2) NOT NULL DEFAULT '0.00',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `total_target` decimal(12,2) NOT NULL DEFAULT '0.00',
  PRIMARY KEY (`id`),
  UNIQUE KEY `branch_name` (`branch_name`)
) ENGINE=InnoDB AUTO_INCREMENT=31 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: chat_attachments
CREATE TABLE `chat_attachments` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `uploaded_by_user_id` int NOT NULL,
  `stored_name` varchar(255) NOT NULL,
  `original_name` varchar(255) NOT NULL,
  `mime_type` varchar(255) DEFAULT NULL,
  `file_size` bigint NOT NULL DEFAULT '0',
  `message_id` bigint DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_chat_attachment_stored_name` (`stored_name`),
  KEY `idx_chat_attachments_message` (`message_id`),
  KEY `idx_chat_attachments_uploaded_by` (`uploaded_by_user_id`,`created_at`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: chat_conversations
CREATE TABLE `chat_conversations` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `conversation_key` varchar(191) NOT NULL,
  `conversation_type` varchar(40) NOT NULL,
  `title` varchar(255) DEFAULT NULL,
  `branch_name` varchar(120) DEFAULT NULL,
  `created_by_user_id` int DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `last_message_at` datetime DEFAULT NULL,
  `last_message_preview` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_chat_conversation_key` (`conversation_key`),
  KEY `idx_chat_conversations_type` (`conversation_type`),
  KEY `idx_chat_conversations_branch` (`branch_name`),
  KEY `idx_chat_conversations_last_message` (`last_message_at`)
) ENGINE=InnoDB AUTO_INCREMENT=498 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: dropdown_options
CREATE TABLE `dropdown_options` (
  `id` int NOT NULL AUTO_INCREMENT,
  `type` varchar(50) DEFAULT NULL,
  `value` varchar(100) DEFAULT NULL,
  `order` int NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_type_value` (`type`,`value`),
  KEY `idx_dropdown_options_order` (`type`,`order`)
) ENGINE=InnoDB AUTO_INCREMENT=66 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: jobs
CREATE TABLE `jobs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `job_number` int NOT NULL,
  `customer_name` varchar(100) DEFAULT NULL,
  `mobile` varchar(20) DEFAULT NULL,
  `device` varchar(100) DEFAULT NULL,
  `model` varchar(100) DEFAULT NULL,
  `serial_number` varchar(100) DEFAULT NULL,
  `complaint` text,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `status` varchar(50) DEFAULT 'Open',
  `branch_name` varchar(100) DEFAULT NULL,
  `priority` varchar(20) DEFAULT NULL,
  `call_type` varchar(50) DEFAULT NULL,
  `backup_required` varchar(50) DEFAULT NULL,
  `complaint_type` varchar(100) DEFAULT NULL,
  `warranty_status` varchar(50) DEFAULT NULL,
  `alt_no` varchar(20) DEFAULT NULL,
  `email` varchar(100) DEFAULT NULL,
  `location` varchar(100) DEFAULT NULL,
  `address` text,
  `pin_code` varchar(10) DEFAULT NULL,
  `received_by` varchar(50) DEFAULT NULL,
  `assigned_engineer` varchar(50) DEFAULT NULL,
  `estimate_amount` decimal(10,2) DEFAULT NULL,
  `accessories_received` text,
  `engineer_remarks` text,
  `photo` varchar(255) DEFAULT NULL,
  `closure_status` varchar(50) DEFAULT NULL,
  `closure_notes` text,
  `closure_date` datetime DEFAULT NULL,
  `closed_by` varchar(50) DEFAULT NULL,
  `status_update_notes` text,
  `status_updated_by` varchar(255) DEFAULT NULL,
  `status_updated_at` datetime DEFAULT NULL,
  `service_charges` decimal(12,2) NOT NULL DEFAULT '0.00',
  `payment_cash` decimal(12,2) NOT NULL DEFAULT '0.00',
  `payment_upi` decimal(12,2) NOT NULL DEFAULT '0.00',
  `payment_card` decimal(12,2) NOT NULL DEFAULT '0.00',
  `spares_billing_status` varchar(32) NOT NULL DEFAULT 'Not Required',
  `spares_invoice_no` varchar(100) DEFAULT NULL,
  `spares_invoice_date` date DEFAULT NULL,
  `spares_billed_by` varchar(255) DEFAULT NULL,
  `spares_billing_notes` text,
  `closure_service_type` varchar(32) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `job_number` (`job_number`),
  UNIQUE KEY `job_number_2` (`job_number`),
  KEY `idx_jobs_branch_name` (`branch_name`),
  KEY `idx_jobs_status` (`status`),
  KEY `idx_jobs_closure_status` (`closure_status`),
  KEY `idx_jobs_assigned_engineer` (`assigned_engineer`),
  KEY `idx_jobs_created_at` (`created_at`),
  KEY `idx_jobs_closure_date` (`closure_date`),
  KEY `idx_jobs_branch_created` (`branch_name`,`created_at`),
  KEY `idx_jobs_branch_closure` (`branch_name`,`closure_date`),
  KEY `idx_jobs_scope_active` (`branch_name`,`closure_status`,`status`)
) ENGINE=InnoDB AUTO_INCREMENT=740 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: onsite_calls
CREATE TABLE `onsite_calls` (
  `id` int NOT NULL AUTO_INCREMENT,
  `customer_name` varchar(255) NOT NULL,
  `phone` varchar(50) NOT NULL,
  `location` varchar(255) NOT NULL,
  `district` varchar(255) NOT NULL,
  `complaint_type` varchar(50) NOT NULL,
  `preferred_service` varchar(50) NOT NULL,
  `priority` varchar(50) NOT NULL,
  `preferred_datetime` datetime NOT NULL,
  `device_model` varchar(255) DEFAULT NULL,
  `complaint_description` text NOT NULL,
  `status` varchar(50) NOT NULL,
  `source` varchar(50) NOT NULL,
  `assigned_branch_id` int DEFAULT NULL,
  `assigned_engineer_id` int DEFAULT NULL,
  `assigned_time` datetime DEFAULT NULL,
  `created_by` varchar(255) DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  `call_type` varchar(20) NOT NULL DEFAULT 'Onsite',
  `lead_source` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_onsite_calls_branch` (`assigned_branch_id`),
  KEY `idx_onsite_calls_engineer` (`assigned_engineer_id`),
  KEY `idx_onsite_calls_created_at` (`created_at`),
  KEY `idx_onsite_calls_status` (`status`),
  KEY `idx_onsite_calls_status_created` (`status`,`created_at`),
  KEY `idx_onsite_calls_call_type` (`call_type`)
) ENGINE=InnoDB AUTO_INCREMENT=2211 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: quotations
CREATE TABLE `quotations` (
  `id` int NOT NULL AUTO_INCREMENT,
  `quote_number` varchar(100) NOT NULL,
  `quote_date` date NOT NULL,
  `branch_name` varchar(255) NOT NULL,
  `customer_name` varchar(255) NOT NULL,
  `customer_mobile` varchar(50) DEFAULT NULL,
  `customer_address` text,
  `customer_gst_no` varchar(100) DEFAULT NULL,
  `engineer_name` varchar(255) DEFAULT NULL,
  `engineer_mobile` varchar(50) DEFAULT NULL,
  `terms_text` text,
  `grand_total` decimal(12,2) NOT NULL DEFAULT '0.00',
  `created_by` varchar(255) DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `quote_number` (`quote_number`),
  KEY `idx_quote_date` (`quote_date`),
  KEY `idx_quote_branch` (`branch_name`)
) ENGINE=InnoDB AUTO_INCREMENT=709 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: revenue_entry_period_locks
CREATE TABLE `revenue_entry_period_locks` (
  `id` int NOT NULL AUTO_INCREMENT,
  `from_date` date NOT NULL,
  `to_date` date NOT NULL,
  `locked_by` varchar(255) DEFAULT NULL,
  `locked_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_rev_entry_lock` (`from_date`,`to_date`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: revenue_report_period_locks
CREATE TABLE `revenue_report_period_locks` (
  `id` int NOT NULL AUTO_INCREMENT,
  `from_date` date NOT NULL,
  `to_date` date NOT NULL,
  `locked_by` varchar(255) DEFAULT NULL,
  `locked_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_revenue_report_period_lock` (`from_date`,`to_date`),
  KEY `idx_revenue_report_period_lock_dates` (`from_date`,`to_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: sequence_counters
CREATE TABLE `sequence_counters` (
  `sequence_key` varchar(100) NOT NULL,
  `last_value` bigint NOT NULL,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`sequence_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: staff_directory
CREATE TABLE `staff_directory` (
  `id` int NOT NULL AUTO_INCREMENT,
  `staff_name` varchar(255) NOT NULL,
  `contact_number` varchar(50) NOT NULL,
  `branch_name` varchar(255) NOT NULL,
  `salary` decimal(12,2) NOT NULL DEFAULT '0.00',
  `esi` decimal(12,2) NOT NULL DEFAULT '0.00',
  `pf` decimal(12,2) NOT NULL DEFAULT '0.00',
  `room` decimal(12,2) NOT NULL DEFAULT '0.00',
  `rent` decimal(12,2) NOT NULL DEFAULT '0.00',
  `joined_date` date NOT NULL,
  `resigned_date` date DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_staff_directory_branch` (`branch_name`),
  KEY `idx_staff_directory_joined_date` (`joined_date`),
  KEY `idx_staff_directory_name` (`staff_name`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: syscare_branch_targets
CREATE TABLE `syscare_branch_targets` (
  `id` int NOT NULL AUTO_INCREMENT,
  `branch_name` varchar(255) NOT NULL,
  `monthly_target` int NOT NULL DEFAULT '30',
  `updated_by` varchar(255) DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_sbt_branch` (`branch_name`)
) ENGINE=InnoDB AUTO_INCREMENT=240 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: syscare_memberships
CREATE TABLE `syscare_memberships` (
  `id` int NOT NULL AUTO_INCREMENT,
  `record_date` date NOT NULL,
  `syscare_id` varchar(100) DEFAULT NULL,
  `customer_name` varchar(255) DEFAULT NULL,
  `contact_number` varchar(50) DEFAULT NULL,
  `branch_name` varchar(255) DEFAULT NULL,
  `incharge` varchar(255) DEFAULT NULL,
  `amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `expiry_date` date DEFAULT NULL,
  `uploaded_by` varchar(255) DEFAULT NULL,
  `uploaded_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `address` text,
  `mail_id` varchar(255) DEFAULT NULL,
  `model_serial` varchar(255) DEFAULT NULL,
  `is_manual` tinyint(1) NOT NULL DEFAULT '0',
  `product_model` varchar(255) DEFAULT NULL,
  `serial_number` varchar(255) DEFAULT NULL,
  `assigned_engineer` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_syscare_id` (`syscare_id`),
  UNIQUE KEY `syscare_id` (`syscare_id`),
  KEY `idx_syscare_record_date` (`record_date`),
  KEY `idx_syscare_branch` (`branch_name`),
  KEY `idx_syscare_branch_record_date` (`branch_name`,`record_date`)
) ENGINE=InnoDB AUTO_INCREMENT=1121 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: user_branches
CREATE TABLE `user_branches` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(50) DEFAULT NULL,
  `branch_name` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=47 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: users
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(50) DEFAULT NULL,
  `password` varchar(255) DEFAULT NULL,
  `role` varchar(50) DEFAULT NULL,
  `profile_picture` varchar(500) DEFAULT NULL,
  `email` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB AUTO_INCREMENT=51 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: job_attachments
CREATE TABLE `job_attachments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `job_id` int NOT NULL,
  `filename` varchar(255) NOT NULL,
  `uploaded_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_job_attachments_job_id` (`job_id`),
  CONSTRAINT `fk_job_attachments_job` FOREIGN KEY (`job_id`) REFERENCES `jobs` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=14 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: job_service_transfers
CREATE TABLE `job_service_transfers` (
  `id` int NOT NULL AUTO_INCREMENT,
  `job_id` int NOT NULL,
  `from_branch_name` varchar(255) NOT NULL,
  `to_branch_name` varchar(255) NOT NULL,
  `specialist_engineer` varchar(255) DEFAULT NULL,
  `service_type` varchar(255) DEFAULT NULL,
  `request_notes` text,
  `status_notes` text,
  `internal_service_charge` decimal(12,2) NOT NULL DEFAULT '0.00',
  `status` varchar(50) NOT NULL DEFAULT 'Sent',
  `sent_by` varchar(255) DEFAULT NULL,
  `updated_by` varchar(255) DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `accepted_at` datetime DEFAULT NULL,
  `completed_at` datetime DEFAULT NULL,
  `returned_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_job_service_transfers_job` (`job_id`),
  KEY `idx_job_service_transfers_target_status` (`to_branch_name`,`status`),
  KEY `idx_job_service_transfers_engineer_status` (`specialist_engineer`,`status`),
  CONSTRAINT `fk_job_service_transfers_job` FOREIGN KEY (`job_id`) REFERENCES `jobs` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: job_status_logs
CREATE TABLE `job_status_logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `job_id` int NOT NULL,
  `status` varchar(255) NOT NULL,
  `notes` text,
  `updated_by` varchar(255) NOT NULL,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_job_status_logs_job` (`job_id`),
  CONSTRAINT `job_status_logs_ibfk_1` FOREIGN KEY (`job_id`) REFERENCES `jobs` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: quick_quotations
CREATE TABLE `quick_quotations` (
  `id` int NOT NULL AUTO_INCREMENT,
  `job_id` int NOT NULL,
  `quote_date` date DEFAULT NULL,
  `engineer_name` varchar(255) DEFAULT NULL,
  `engineer_mobile` varchar(50) DEFAULT NULL,
  `created_by` varchar(255) DEFAULT NULL,
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `job_id` (`job_id`),
  CONSTRAINT `fk_quick_quote_job` FOREIGN KEY (`job_id`) REFERENCES `jobs` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: used_spares
CREATE TABLE `used_spares` (
  `id` int NOT NULL AUTO_INCREMENT,
  `job_id` int NOT NULL,
  `spare_name` varchar(255) NOT NULL,
  `amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_used_spares_job` (`job_id`),
  CONSTRAINT `fk_used_spares_job` FOREIGN KEY (`job_id`) REFERENCES `jobs` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=42 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: onsite_call_attachments
CREATE TABLE `onsite_call_attachments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `call_id` int NOT NULL,
  `filename` varchar(255) NOT NULL,
  `media_kind` varchar(16) NOT NULL,
  `mime_type` varchar(64) NOT NULL,
  `uploaded_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_onsite_call_attachments_call_id` (`call_id`),
  CONSTRAINT `onsite_call_attachments_ibfk_1` FOREIGN KEY (`call_id`) REFERENCES `onsite_calls` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: onsite_call_closures
CREATE TABLE `onsite_call_closures` (
  `id` int NOT NULL AUTO_INCREMENT,
  `call_id` int NOT NULL,
  `final_status` varchar(50) NOT NULL,
  `close_reason` text,
  `completion_type` varchar(32) DEFAULT NULL,
  `narration` text,
  `service_charges` decimal(12,2) NOT NULL,
  `engineer_id` int DEFAULT NULL,
  `product_value` decimal(12,2) NOT NULL,
  `customer_price` decimal(12,2) NOT NULL,
  `closed_by_brand` varchar(32) DEFAULT NULL,
  `payment_mode` varchar(16) DEFAULT NULL,
  `payment_status` varchar(32) DEFAULT NULL,
  `closed_by_user` varchar(255) DEFAULT NULL,
  `closed_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_onsite_call_closures_call_id` (`call_id`),
  KEY `idx_onsite_call_closures_payment_status` (`payment_status`),
  CONSTRAINT `onsite_call_closures_ibfk_1` FOREIGN KEY (`call_id`) REFERENCES `onsite_calls` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: onsite_call_logs
CREATE TABLE `onsite_call_logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `call_id` int NOT NULL,
  `action` varchar(100) NOT NULL,
  `description` text NOT NULL,
  `done_by` varchar(255) DEFAULT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_onsite_call_logs_call_id` (`call_id`),
  CONSTRAINT `onsite_call_logs_ibfk_1` FOREIGN KEY (`call_id`) REFERENCES `onsite_calls` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=5254 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: onsite_call_notes
CREATE TABLE `onsite_call_notes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `call_id` int NOT NULL,
  `note` text NOT NULL,
  `created_by` varchar(255) DEFAULT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_onsite_call_notes_call_id` (`call_id`),
  CONSTRAINT `onsite_call_notes_ibfk_1` FOREIGN KEY (`call_id`) REFERENCES `onsite_calls` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: onsite_call_service_transfers
CREATE TABLE `onsite_call_service_transfers` (
  `id` int NOT NULL AUTO_INCREMENT,
  `call_id` int NOT NULL,
  `from_branch_id` int DEFAULT NULL,
  `to_branch_id` int NOT NULL,
  `service_engineer_id` int DEFAULT NULL,
  `service_type` varchar(100) NOT NULL,
  `notes` text,
  `internal_service_charge` decimal(12,2) NOT NULL,
  `status` varchar(32) NOT NULL,
  `sent_by_user` varchar(255) DEFAULT NULL,
  `sent_at` datetime NOT NULL,
  `completed_at` datetime DEFAULT NULL,
  `returned_at` datetime DEFAULT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_onsite_call_service_transfers_target_branch` (`to_branch_id`),
  KEY `idx_onsite_call_service_transfers_call_status` (`call_id`,`status`),
  KEY `ix_onsite_call_service_transfers_call_id` (`call_id`),
  KEY `ix_onsite_call_service_transfers_to_branch_id` (`to_branch_id`),
  CONSTRAINT `onsite_call_service_transfers_ibfk_1` FOREIGN KEY (`call_id`) REFERENCES `onsite_calls` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: quotation_items
CREATE TABLE `quotation_items` (
  `id` int NOT NULL AUTO_INCREMENT,
  `quotation_id` int NOT NULL,
  `line_no` int NOT NULL DEFAULT '1',
  `item_name` varchar(255) NOT NULL,
  `narration` text,
  `qty` decimal(12,2) NOT NULL DEFAULT '0.00',
  `amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `final_amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_quotation_items_quote` (`quotation_id`),
  CONSTRAINT `fk_quotation_items_quote` FOREIGN KEY (`quotation_id`) REFERENCES `quotations` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=742 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: chat_conversation_members
CREATE TABLE `chat_conversation_members` (
  `conversation_id` bigint NOT NULL,
  `user_id` int NOT NULL,
  `joined_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `last_read_message_id` bigint DEFAULT NULL,
  `last_read_at` datetime DEFAULT NULL,
  `is_hidden` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`conversation_id`,`user_id`),
  KEY `idx_chat_members_user` (`user_id`),
  KEY `idx_chat_members_last_read` (`user_id`,`last_read_message_id`),
  CONSTRAINT `fk_chat_members_conversation` FOREIGN KEY (`conversation_id`) REFERENCES `chat_conversations` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_chat_members_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: chat_messages
CREATE TABLE `chat_messages` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `conversation_id` bigint NOT NULL,
  `sender_user_id` int NOT NULL,
  `receiver_user_id` int DEFAULT NULL,
  `branch_name` varchar(120) DEFAULT NULL,
  `message_text` text,
  `message_type` varchar(20) NOT NULL DEFAULT 'text',
  `attachment_original_name` varchar(255) DEFAULT NULL,
  `attachment_stored_name` varchar(255) DEFAULT NULL,
  `attachment_mime_type` varchar(255) DEFAULT NULL,
  `is_read` tinyint(1) NOT NULL DEFAULT '0',
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `scope_type` varchar(20) DEFAULT NULL,
  `room_name` varchar(255) DEFAULT NULL,
  `conversation_key` varchar(255) DEFAULT NULL,
  `sender_username` varchar(255) DEFAULT NULL,
  `sender_role` varchar(50) DEFAULT NULL,
  `sender_branch` varchar(255) DEFAULT NULL,
  `recipient_user_id` int DEFAULT NULL,
  `recipient_username` varchar(255) DEFAULT NULL,
  `attachment_id` bigint DEFAULT NULL,
  `is_broadcast` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `idx_chat_messages_conversation_created` (`conversation_id`,`created_at`,`id`),
  KEY `idx_chat_messages_sender_created` (`sender_user_id`,`created_at`),
  KEY `idx_chat_messages_receiver` (`receiver_user_id`),
  KEY `idx_chat_messages_branch` (`branch_name`),
  KEY `idx_chat_messages_room_time` (`room_name`,`created_at`),
  KEY `idx_chat_messages_conversation_time` (`conversation_key`,`created_at`),
  KEY `idx_chat_messages_branch_time` (`branch_name`,`created_at`),
  KEY `idx_chat_messages_recipient_time` (`recipient_user_id`,`created_at`),
  KEY `idx_chat_messages_conversation` (`conversation_id`,`created_at`),
  KEY `idx_chat_messages_sender` (`sender_user_id`,`created_at`),
  CONSTRAINT `fk_chat_messages_conversation` FOREIGN KEY (`conversation_id`) REFERENCES `chat_conversations` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_chat_messages_receiver` FOREIGN KEY (`receiver_user_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_chat_messages_sender` FOREIGN KEY (`sender_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=18 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: chat_user_presence
CREATE TABLE `chat_user_presence` (
  `user_id` int NOT NULL,
  `is_online` tinyint(1) NOT NULL DEFAULT '0',
  `connection_count` int NOT NULL DEFAULT '0',
  `last_seen_at` datetime DEFAULT NULL,
  `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`),
  KEY `idx_chat_presence_online` (`is_online`,`updated_at`),
  CONSTRAINT `fk_chat_presence_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: password_reset_tokens
CREATE TABLE `password_reset_tokens` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `token_hash` char(64) NOT NULL,
  `requested_ip` varchar(255) DEFAULT NULL,
  `expires_at` datetime NOT NULL,
  `used_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_password_reset_tokens_hash` (`token_hash`),
  KEY `idx_password_reset_tokens_user` (`user_id`),
  KEY `idx_password_reset_tokens_expires` (`expires_at`),
  CONSTRAINT `fk_password_reset_tokens_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: quick_quotation_items
CREATE TABLE `quick_quotation_items` (
  `id` int NOT NULL AUTO_INCREMENT,
  `quotation_id` int NOT NULL,
  `line_no` int NOT NULL DEFAULT '1',
  `item_name` varchar(255) DEFAULT NULL,
  `narration` text,
  `qty` decimal(12,2) NOT NULL DEFAULT '0.00',
  `amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  `final_amount` decimal(12,2) NOT NULL DEFAULT '0.00',
  PRIMARY KEY (`id`),
  KEY `fk_quick_quote_item_quote` (`quotation_id`),
  CONSTRAINT `fk_quick_quote_item_quote` FOREIGN KEY (`quotation_id`) REFERENCES `quick_quotations` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS=1;
