-- Research Engine v2 Initial Schema (Migration 001)
-- All tables carry created_at. IDs are stable. Foreign key constraints and indexes included.

CREATE TABLE IF NOT EXISTS meta (
    schema_version INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    scope TEXT,
    time_window_months INTEGER DEFAULT 36,
    status TEXT CHECK(status IN ('draft', 'active', 'retired')) DEFAULT 'active',
    version INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    lane TEXT CHECK(lane IN ('academic', 'enterprise', 'practitioner')) NOT NULL,
    source_type TEXT CHECK(source_type IN (
        'peer_reviewed', 'preprint', 'vendor_blog', 'customer_case_study',
        'analyst_survey', 'regulator_standard', 'filing', 'incident_report',
        'job_posting', 'practitioner_note'
    )) NOT NULL,
    org TEXT,
    title TEXT NOT NULL,
    url TEXT,
    doi TEXT,
    venue TEXT,
    venue_tier TEXT CHECK(venue_tier IN ('verified', 'reputable_preprint', 'unverified', 'vendor', 'n/a')) DEFAULT 'unverified',
    pub_date TEXT,
    retrieved_at TEXT,
    content_hash TEXT,
    extraction_depth TEXT CHECK(extraction_depth IN ('abstract_only', 'full_text', 'structured_data')) DEFAULT 'abstract_only',
    commercial_stake TEXT CHECK(commercial_stake IN ('none', 'vendor', 'sponsored', 'unknown')) DEFAULT 'unknown',
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claims (
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
    status TEXT CHECK(status IN ('auto', 'approved', 'edited', 'rejected')) DEFAULT 'auto',
    observations_count INTEGER DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claim_links (
    claim_a TEXT REFERENCES claims(id),
    claim_b TEXT REFERENCES claims(id),
    relation TEXT CHECK(relation IN ('corroborates', 'contradicts', 'supersedes', 'duplicate_source')) NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (claim_a, claim_b, relation)
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    config_json TEXT,
    code_version TEXT,
    model_ids TEXT,
    question_ids TEXT,
    seed INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS search_log (
    id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES runs(id),
    question_id TEXT REFERENCES questions(id),
    lane TEXT NOT NULL,
    query TEXT NOT NULL,
    source_api TEXT NOT NULL,
    result_count INTEGER NOT NULL DEFAULT 0,
    executed_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gap_matrix (
    id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES runs(id),
    question_id TEXT REFERENCES questions(id),
    academic_state TEXT,
    enterprise_state TEXT,
    field_state TEXT,
    outcome INTEGER CHECK(outcome IN (1, 2, 3, 4)) NOT NULL,
    rationale TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id TEXT PRIMARY KEY,
    gate TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    action TEXT NOT NULL,
    before_json TEXT,
    after_json TEXT,
    reason TEXT,
    reviewer TEXT NOT NULL,
    ts TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outputs (
    id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES runs(id),
    kind TEXT CHECK(kind IN ('field_note', 'strategy_doc', 'json_export')) NOT NULL,
    version INTEGER DEFAULT 1,
    path TEXT,
    status TEXT CHECK(status IN ('draft', 'in_review', 'published', 'blocked', 'legacy-ungraded')) DEFAULT 'draft',
    score_json TEXT,
    gates_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS output_sentences (
    id TEXT PRIMARY KEY,
    output_id TEXT REFERENCES outputs(id),
    ordinal INTEGER NOT NULL,
    text TEXT NOT NULL,
    type TEXT CHECK(type IN ('assertive', 'opinion', 'field', 'heading')) NOT NULL,
    claim_ids_json TEXT,
    strength_verb TEXT,
    checks_json TEXT,
    created_at TEXT NOT NULL
);

-- Foreign Key Indexes for Performance and Integrity
CREATE INDEX IF NOT EXISTS idx_claims_question ON claims(question_id);
CREATE INDEX IF NOT EXISTS idx_claims_source ON claims(source_id);
CREATE INDEX IF NOT EXISTS idx_claims_grade ON claims(grade);
CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status);
CREATE INDEX IF NOT EXISTS idx_sources_lane ON sources(lane);
CREATE INDEX IF NOT EXISTS idx_sources_doi ON sources(doi);
CREATE INDEX IF NOT EXISTS idx_search_log_question ON search_log(question_id);
CREATE INDEX IF NOT EXISTS idx_reviews_object ON reviews(object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_output_sentences_output ON output_sentences(output_id);
