-- Add normalized_name column for semantic dedup of weekly_events.
-- Two newsletters may describe the same real-world event with slightly
-- different titles (e.g. "Affordable Homeownership Application Deadline"
-- vs "Affordable Homeownership Application Deadline (43 Hemenway Street)").
-- Normalizing lets us collapse those into one row.

ALTER TABLE weekly_events ADD COLUMN normalized_name VARCHAR(500);

UPDATE weekly_events
SET normalized_name = TRIM(REGEXP_REPLACE(
    REGEXP_REPLACE(LOWER(event_name), '\\([^)]*\\)', ''),
    '[[:space:]]+', ' '
))
WHERE normalized_name IS NULL;

DELETE e1 FROM weekly_events e1
INNER JOIN weekly_events e2
WHERE e1.id > e2.id
  AND e1.normalized_name = e2.normalized_name
  AND (e1.start_date <=> e2.start_date);

ALTER TABLE weekly_events ADD UNIQUE KEY unique_event_v2 (normalized_name, start_date);
