ALTER TABLE interaction_log ADD COLUMN user_id CHAR(36) NULL;
ALTER TABLE interaction_log ADD COLUMN thread_id CHAR(36) NULL;
ALTER TABLE interaction_log ADD COLUMN message_id CHAR(36) NULL;
