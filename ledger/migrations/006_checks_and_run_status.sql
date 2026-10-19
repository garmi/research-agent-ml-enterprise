-- Forward-only migration 006: Handoff-check verdicts and persisted run status (DEC-016)
ALTER TABLE runs ADD COLUMN status TEXT DEFAULT 'RUNNING';
ALTER TABLE runs ADD COLUMN status_reason TEXT;
-- Runs recorded before this migration have no known outcome; do not let the default call them RUNNING.
UPDATE runs SET status = 'UNKNOWN', status_reason = 'Run recorded before run status was tracked (migration 006).';

CREATE TABLE IF NOT EXISTS check_verdicts (
    id TEXT PRIMARY KEY,
    check_id TEXT NOT NULL,
    run_id TEXT REFERENCES runs(id),
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    model_verdict TEXT,
    rule_verdict TEXT,
    rule_decisive INTEGER NOT NULL DEFAULT 0,
    final TEXT NOT NULL,
    reason_plain TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 0 CHECK(attempt IN (0, 1)),
    model_id TEXT,
    prompt_hash TEXT,
    details_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_check_verdicts_run ON check_verdicts(run_id, check_id);
