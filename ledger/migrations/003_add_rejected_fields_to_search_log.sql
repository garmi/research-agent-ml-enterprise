-- Forward-only migration 003: Add rejected_reason and details_json to search_log
ALTER TABLE search_log ADD COLUMN rejected_reason TEXT;
ALTER TABLE search_log ADD COLUMN details_json TEXT;
