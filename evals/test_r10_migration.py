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
