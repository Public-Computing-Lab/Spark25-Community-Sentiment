CREATE TABLE IF NOT EXISTS interaction_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(255),
    app_version VARCHAR(50),
    data_selected TEXT,
    data_attributes TEXT,
    prompt_preamble TEXT,
    client_query TEXT,
    app_response TEXT,
    client_response_rating VARCHAR(50),
    flagged BOOLEAN DEFAULT FALSE,
    flag_reason VARCHAR(100),
    flag_details TEXT,
    flagged_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
