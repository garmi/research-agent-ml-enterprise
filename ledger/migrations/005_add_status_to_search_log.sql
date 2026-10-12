-- Forward-only migration 005: Add status column to search_log and allow text outcomes in gap_matrix
ALTER TABLE search_log ADD COLUMN status TEXT CHECK(status IN ('searched_ok', 'searched_error', 'not_implemented', 'not_searched', 'skipped_by_scope')) DEFAULT 'searched_ok';

-- Recreate gap_matrix to allow outcome as TEXT/VARCHAR or integer (e.g. 1, 2, 3, 4, 'Practice not assessed')
CREATE TABLE IF NOT EXISTS gap_matrix_new (
    id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES runs(id),
    question_id TEXT REFERENCES questions(id),
    academic_state TEXT,
    enterprise_state TEXT,
    field_state TEXT,
    outcome TEXT NOT NULL,
    rationale TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL
);

INSERT INTO gap_matrix_new (id, run_id, question_id, academic_state, enterprise_state, field_state, outcome, rationale, status, created_at)
SELECT id, run_id, question_id, academic_state, enterprise_state, field_state, CAST(outcome AS TEXT), rationale, status, created_at
FROM gap_matrix;

DROP TABLE gap_matrix;
ALTER TABLE gap_matrix_new RENAME TO gap_matrix;

CREATE INDEX IF NOT EXISTS idx_gap_matrix_question ON gap_matrix(question_id);
