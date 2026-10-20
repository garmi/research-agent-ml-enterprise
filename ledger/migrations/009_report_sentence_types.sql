-- Forward-only migration 009: the question-shaped report's sentence types (S19): synthesis, tension, gap, implication.

CREATE TABLE IF NOT EXISTS output_sentences_new (
    id TEXT PRIMARY KEY,
    output_id TEXT REFERENCES outputs(id),
    ordinal INTEGER NOT NULL,
    text TEXT NOT NULL,
    type TEXT CHECK(type IN ('assertive', 'opinion', 'field', 'heading', 'signal', 'risk', 'roadmap', 'finding', 'negative_finding', 'summary', 'synthesis', 'tension', 'gap', 'implication')) NOT NULL,
    claim_ids_json TEXT,
    strength_verb TEXT,
    checks_json TEXT,
    created_at TEXT NOT NULL
);

INSERT INTO output_sentences_new (id, output_id, ordinal, text, type, claim_ids_json, strength_verb, checks_json, created_at)
SELECT id, output_id, ordinal, text, type, claim_ids_json, strength_verb, checks_json, created_at
FROM output_sentences;

DROP TABLE output_sentences;

ALTER TABLE output_sentences_new RENAME TO output_sentences;

CREATE INDEX IF NOT EXISTS idx_output_sentences_output ON output_sentences(output_id);
CREATE INDEX IF NOT EXISTS idx_output_sentences_type ON output_sentences(type);
