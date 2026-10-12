"""Regression Test R10: Schema migration on a populated older-version database.

Acceptance:
- Migration engine runs cleanly on pre-populated database.
- An automatic timestamped backup is generated prior to applying migrations.
- Zero data loss: all pre-existing rows and values remain intact.
- PRAGMA integrity_check passes and journal_mode is WAL.
- schema_version in meta table is updated.
"""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest
from src.ledger.db import get_connection
from src.ledger.migrations import apply_migrations, get_current_schema_version


def test_r10_migration_populated_old_db():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_ledger.db")
        backups_dir = os.path.join(tmp_dir, "backups")

        # Step 1: Create an older/v0 database with populated data
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE legacy_papers (id TEXT PRIMARY KEY, title TEXT, notes TEXT);")
        conn.execute(
            "INSERT INTO legacy_papers VALUES (?, ?, ?);",
            ("p1", "Old Study on Dev Productivity", "Baseline legacy record 1"),
        )
        conn.execute(
            "INSERT INTO legacy_papers VALUES (?, ?, ?);",
            ("p2", "Spec-Driven Experiment", "Baseline legacy record 2"),
        )
        conn.commit()
        conn.close()

        # Step 2: Apply v2 forward-only migrations
        latest_version = apply_migrations(
            db_path=db_path,
            migrations_dir="ledger/migrations",
            backups_dir=backups_dir,
        )

        assert latest_version >= 1, f"Expected latest schema version >= 1, got {latest_version}"

        # Step 3: Verify pre-migration backup was created
        backup_files = list(Path(backups_dir).glob("pre_migration_*.db"))
        assert len(backup_files) == 1, f"Expected 1 pre-migration backup, found {len(backup_files)}"
        assert backup_files[0].stat().st_size > 0, "Backup file should not be empty"

        # Step 4: Verify zero data loss on pre-existing data
        conn_migrated = get_connection(db_path, verify_integrity=True)
        cursor = conn_migrated.execute("SELECT COUNT(*) FROM legacy_papers;")
        count = cursor.fetchone()[0]
        assert count == 2, f"Expected 2 legacy records to be preserved, found {count}"

        p1 = conn_migrated.execute("SELECT * FROM legacy_papers WHERE id = 'p1';").fetchone()
        assert p1["title"] == "Old Study on Dev Productivity"

        # Step 5: Verify new schema tables exist and meta is updated
        v = get_current_schema_version(conn_migrated)
        assert v == latest_version

        # Verify tables created
        for expected_table in ["meta", "questions", "sources", "claims", "claim_links", "runs", "search_log", "gap_matrix", "reviews", "outputs", "output_sentences"]:
            cur = conn_migrated.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?;",
                (expected_table,),
            )
            assert cur.fetchone() is not None, f"Expected table {expected_table} to exist after migration"

        # Step 6: Verify WAL mode
        journal_mode = conn_migrated.execute("PRAGMA journal_mode;").fetchone()[0]
        assert journal_mode.lower() == "wal"

        conn_migrated.close()


def test_quarantine_legacy_pre_a1_records():
    """Verify that outputs, claims, and runs created before commit A1 are quarantined as legacy-ungraded and export blocked."""
    from src.ledger.quarantine import quarantine_pre_a1_records
    from src.publish.export_policy import evaluate_export_permissions
    from src.ledger.models import Question, Run, Source, Claim, OutputDoc

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "quarantine_test.db")
        apply_migrations(db_path=db_path)

        conn = get_connection(db_path)
        # 1. Insert pre-A1 data (created 2026-10-10)
        conn.execute(
            "INSERT INTO questions (id, text, scope, time_window_months, status, version, created_at) "
            "VALUES ('q_old', 'Old question', 'enterprise', 36, 'active', 1, '2026-10-10T10:00:00Z');"
        )
        conn.execute(
            "INSERT INTO runs (id, started_at, config_json, code_version, model_ids, question_ids, seed, created_at) "
            "VALUES ('run_old', '2026-10-10T10:00:00Z', '{}', 'v1.0', '{}', '[\"q_old\"]', 42, '2026-10-10T10:00:00Z');"
        )
        conn.execute(
            "INSERT INTO sources (id, lane, source_type, org, title, url, doi, venue, venue_tier, pub_date, retrieved_at, content_hash, extraction_depth, commercial_stake, status, created_at) "
            "VALUES ('s_old', 'academic', 'peer_reviewed', 'IEEE', 'Fake Paper', 'https://doi.org/10.1109/fake', '10.1109/fake', 'ICSE', 'verified', '2024', '2026-10-10T10:00:00Z', 'hash', 'abstract_only', 'none', 'active', '2026-10-10T10:00:00Z');"
        )
        conn.execute(
            "INSERT INTO claims (id, question_id, source_id, text, source_excerpt, grade, status, observations_count, created_at) "
            "VALUES ('c_old', 'q_old', 's_old', 'Productivity increases by 34%', 'excerpt 34%', 'strong', 'approved', 1, '2026-10-10T10:00:00Z');"
        )
        conn.execute(
            "INSERT INTO outputs (id, run_id, kind, version, path, status, created_at) "
            "VALUES ('out_old', 'run_old', 'field_note', 1, 'outputs/reports/old.md', 'published', '2026-10-10T10:00:00Z');"
        )

        # 2. Insert post-A1 data (created 2026-10-12)
        conn.execute(
            "INSERT INTO questions (id, text, scope, time_window_months, status, version, created_at) "
            "VALUES ('q_new', 'New question', 'enterprise', 36, 'active', 1, '2026-10-12T10:00:00Z');"
        )
        conn.execute(
            "INSERT INTO runs (id, started_at, config_json, code_version, model_ids, question_ids, seed, created_at) "
            "VALUES ('run_new', '2026-10-12T10:00:00Z', '{}', 'v2.0', '{}', '[\"q_new\"]', 42, '2026-10-12T10:00:00Z');"
        )
        conn.execute(
            "INSERT INTO outputs (id, run_id, kind, version, path, status, created_at) "
            "VALUES ('out_new', 'run_new', 'field_note', 1, 'outputs/reports/new.md', 'draft', '2026-10-12T10:00:00Z');"
        )
        conn.commit()
        conn.close()

        # Execute quarantine
        summary = quarantine_pre_a1_records(db_path=db_path)

        assert summary["outputs_quarantined"] >= 1
        assert "out_old" in summary["quarantined_output_ids"]
        assert "out_new" not in summary["quarantined_output_ids"]

        conn = get_connection(db_path)
        out_old_status = conn.execute("SELECT status FROM outputs WHERE id = 'out_old';").fetchone()[0]
        out_new_status = conn.execute("SELECT status FROM outputs WHERE id = 'out_new';").fetchone()[0]
        claim_old_status = conn.execute("SELECT status FROM claims WHERE id = 'c_old';").fetchone()[0]
        run_old_config = conn.execute("SELECT config_json FROM runs WHERE id = 'run_old';").fetchone()[0]
        conn.close()

        assert out_old_status == "legacy-ungraded"
        assert out_new_status == "draft"
        assert claim_old_status == "legacy-ungraded"
        assert "legacy-ungraded" in run_old_config

        # Verify export policy strictly blocks any export of legacy-ungraded outputs
        perms = evaluate_export_permissions(status="legacy-ungraded", allowed=True)
        assert perms.is_blocked is True
        assert perms.can_download_draft is False
        assert perms.can_download_full is False
        assert perms.can_download_deck is False
        assert perms.can_download_linkedin is False
        assert perms.can_download_csv is False

