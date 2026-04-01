ALTER TABLE interaction_log ADD COLUMN client_response_rating VARCHAR(50) NULL;
ALTER TABLE interaction_log ADD COLUMN flagged BOOLEAN DEFAULT FALSE;
ALTER TABLE interaction_log ADD COLUMN flag_reason VARCHAR(100) NULL;
ALTER TABLE interaction_log ADD COLUMN flag_details TEXT NULL;
ALTER TABLE interaction_log ADD COLUMN flagged_at TIMESTAMP NULL;
