"""Forward-only schema migration and durability engine for Research Engine v2.

Mandatory durability requirements:
1. schema_version tracking in `meta` table.
2. Forward-only migrations from `ledger/migrations/`.
3. Automatic timestamped backup before every migration and bulk write.
4. Retention of last N backups.
5. SQLite WAL mode and integrity checks.
"""

from __future__ import annotations

import datetime
import glob
import logging
import os
import re
import shutil
import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple

from src.ledger.db import get_connection

logger = logging.getLogger(__name__)

DEFAULT_MIGRATIONS_DIR = "ledger/migrations"
DEFAULT_BACKUPS_DIR = "ledger/backups"


def default_backups_dir() -> str:
    """Backups directory: LEDGER_BACKUPS_DIR when set, otherwise DEFAULT_BACKUPS_DIR."""
    return os.getenv("LEDGER_BACKUPS_DIR") or DEFAULT_BACKUPS_DIR


def create_backup(
    db_path: str,
    backups_dir: Optional[str] = None,
    keep_last_n: int = 10,
    prefix: str = "backup",
) -> Optional[str]:
    """Create a timestamped backup of the database before migrations or bulk writes.

    Rotates older backups to keep the last `keep_last_n`.
    """
    if backups_dir is None or backups_dir == DEFAULT_BACKUPS_DIR or backups_dir == "ledger/backups":
        backups_dir = default_backups_dir()

    source = Path(db_path)
    if not source.exists() or source.stat().st_size == 0:
        return None

    target_dir = Path(backups_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_filename = f"{prefix}_{source.stem}_{timestamp}.db"
    backup_path = target_dir / backup_filename

    # SQLite VACUUM INTO is the cleanest online backup, or shutil.copy2
    try:
        conn = sqlite3.connect(str(source))
        conn.execute(f"VACUUM INTO '{backup_path.resolve()}';")
        conn.close()
    except Exception:
        # Fallback to copy2 if VACUUM INTO fails (e.g. older sqlite)
        shutil.copy2(source, backup_path)

    # Rotate old backups
    pattern = str(target_dir / f"{prefix}_{source.stem}_*.db")
    existing_backups = sorted(glob.glob(pattern))
    if len(existing_backups) > keep_last_n:
        for old_backup in existing_backups[:-keep_last_n]:
            try:
                os.remove(old_backup)
            except OSError:
                pass

    return str(backup_path)


def get_current_schema_version(conn: sqlite3.Connection) -> int:
    """Return the current schema version from the meta table, or 0 if uninitialized."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meta';")
        if not cursor.fetchone():
            return 0
        cursor.execute("SELECT MAX(schema_version) FROM meta;")
        row = cursor.fetchone()
        if row and row[0] is not None:
            return int(row[0])
        return 0
    except sqlite3.Error:
        return 0


FALLBACK_LATEST_SCHEMA_SQL = """
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
    status TEXT CHECK(status IN ('auto', 'approved', 'edited', 'rejected', 'legacy-ungraded')) DEFAULT 'auto',
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
    created_at TEXT NOT NULL,
    status TEXT DEFAULT 'RUNNING',
    status_reason TEXT
);

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

CREATE TABLE IF NOT EXISTS search_log (
    id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES runs(id),
    question_id TEXT REFERENCES questions(id),
    lane TEXT NOT NULL,
    query TEXT NOT NULL,
    source_api TEXT NOT NULL,
    result_count INTEGER NOT NULL DEFAULT 0,
    status TEXT CHECK(status IN ('searched_ok', 'searched_error', 'not_implemented', 'not_searched', 'skipped_by_scope')) DEFAULT 'searched_ok',
    executed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    rejected_reason TEXT,
    details_json TEXT
);

CREATE TABLE IF NOT EXISTS gap_matrix (
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
    type TEXT CHECK(type IN ('assertive', 'opinion', 'field', 'heading', 'signal', 'risk', 'roadmap', 'finding', 'negative_finding')) NOT NULL,
    claim_ids_json TEXT,
    strength_verb TEXT,
    checks_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_claims_question ON claims(question_id);
CREATE INDEX IF NOT EXISTS idx_claims_source ON claims(source_id);
CREATE INDEX IF NOT EXISTS idx_claims_grade ON claims(grade);
CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status);
CREATE INDEX IF NOT EXISTS idx_sources_lane ON sources(lane);
CREATE INDEX IF NOT EXISTS idx_sources_doi ON sources(doi);
CREATE INDEX IF NOT EXISTS idx_search_log_question ON search_log(question_id);
CREATE INDEX IF NOT EXISTS idx_reviews_object ON reviews(object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_output_sentences_output ON output_sentences(output_id);
CREATE INDEX IF NOT EXISTS idx_output_sentences_type ON output_sentences(type);
CREATE INDEX IF NOT EXISTS idx_gap_matrix_question ON gap_matrix(question_id);
CREATE INDEX IF NOT EXISTS idx_check_verdicts_run ON check_verdicts(run_id, check_id);
"""


def list_migration_files(migrations_dir: str = DEFAULT_MIGRATIONS_DIR) -> List[Tuple[int, Path]]:
    """List and sort migration sql files by version prefix (e.g. 001_initial_schema.sql -> 1)."""
    dir_path = Path(migrations_dir)
    if not dir_path.exists():
        repo_root_migrations = Path(__file__).resolve().parent.parent.parent / "ledger" / "migrations"
        if migrations_dir == DEFAULT_MIGRATIONS_DIR and repo_root_migrations.exists():
            dir_path = repo_root_migrations
        else:
            return []

    migrations: List[Tuple[int, Path]] = []
    pattern = re.compile(r"^(\d+)_.+\.sql$")
    for file_path in dir_path.glob("*.sql"):
        match = pattern.match(file_path.name)
        if match:
            version = int(match.group(1))
            migrations.append((version, file_path))

    migrations.sort(key=lambda x: x[0])
    return migrations


def apply_migrations(
    db_path: str,
    migrations_dir: str = DEFAULT_MIGRATIONS_DIR,
    backups_dir: Optional[str] = None,
    keep_last_n: int = 10,
) -> int:
    """Apply all pending forward migrations to the target database.

    Creates an automatic timestamped backup prior to applying any new migration.

    Returns:
        The latest schema version after migrations.
    """
    if backups_dir is None or backups_dir == DEFAULT_BACKUPS_DIR or backups_dir == "ledger/backups":
        backups_dir = default_backups_dir()

    conn = get_connection(db_path, verify_integrity=False)
    current_version = get_current_schema_version(conn)
    all_migrations = list_migration_files(migrations_dir)

    pending = [m for m in all_migrations if m[0] > current_version]
    if not pending:
        if current_version == 0:
            # Fallback embedded schema when SQL files are unavailable on disk
            try:
                conn.executescript(FALLBACK_LATEST_SCHEMA_SQL)
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                conn.execute(
                    "INSERT INTO meta (schema_version, created_at) VALUES (?, ?);",
                    (6, now_iso),
                )
                conn.commit()
                return 6
            finally:
                conn.close()
        conn.close()
        return current_version

    # Perform backup before modifying schema
    conn.close()
    create_backup(db_path, backups_dir=backups_dir, keep_last_n=keep_last_n, prefix="pre_migration")

    conn = get_connection(db_path, verify_integrity=True)
    try:
        for version, migration_file in pending:
            logger.info("Applying migration %03d from %s", version, migration_file.name)
            with open(migration_file, "r", encoding="utf-8") as f:
                sql_script = f.read()

            conn.executescript(sql_script)

            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO meta (schema_version, created_at) VALUES (?, ?);",
                (version, now_iso),
            )
            conn.commit()
            current_version = version

        return current_version
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Migration failed at version {version}: {e}") from e
    finally:
        conn.close()
