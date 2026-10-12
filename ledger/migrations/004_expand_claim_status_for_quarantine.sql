-- Forward-only Migration 004: Expand claims.status CHECK constraint to include 'legacy-ungraded'

CREATE TABLE IF NOT EXISTS claims_new (
    id TEXT PRIMARY KEY,
    question_id TEXT REFERENCES questions(id),
    source_id TEXT REFERENCES sources(id),
    text TEXT NOT NULL,
    source_excerpt TEXT NOT NULL,
    value_json TEXT,
    entity TEXT,
    entity_match TEXT CHECK(entity_match IN ('exact', 'family', 'topic_level', 'mismatch')) DEFAULT 'topic_level',
    study_type TEXT CHECK(study_type IN (
        'field_experiment', 'controlled_study', 'survey_with_method',
        'case_study', 'position_paper', 'conceptual_framework',
        'vendor_assertion', 'filing_disclosure', 'practitioner_observation'
    )) DEFAULT 'position_paper',
    context_json TEXT,
    claim_date TEXT,
    extraction_model TEXT,
    extraction_confidence REAL DEFAULT 1.0,
    grade TEXT CHECK(grade IN ('strong', 'moderate', 'weak', 'vendor_claim', 'anecdote')) DEFAULT 'weak',
    grade_reasons_json TEXT,
    status TEXT CHECK(status IN ('auto', 'approved', 'edited', 'rejected', 'legacy-ungraded')) DEFAULT 'auto',
    observations_count INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);

INSERT INTO claims_new (id, question_id, source_id, text, source_excerpt, value_json, entity, entity_match, study_type, context_json, claim_date, extraction_model, extraction_confidence, grade, grade_reasons_json, status, observations_count, created_at)
SELECT id, question_id, source_id, text, source_excerpt, value_json, entity, entity_match, study_type, context_json, claim_date, extraction_model, extraction_confidence, grade, grade_reasons_json, status, observations_count, created_at
FROM claims;

DROP TABLE claims;

ALTER TABLE claims_new RENAME TO claims;

CREATE INDEX IF NOT EXISTS idx_claims_question ON claims(question_id);
CREATE INDEX IF NOT EXISTS idx_claims_source ON claims(source_id);
CREATE INDEX IF NOT EXISTS idx_claims_grade ON claims(grade);
CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status);
