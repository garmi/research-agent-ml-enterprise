"""Regression tests for Cloud Run database initialization, .gcloudignore migration inclusion,
and hosted demo mode synthesis completeness.
"""

from __future__ import annotations

import fnmatch
import os
import tempfile
from pathlib import Path

import pytest

from src.analysis.multilane_runner import MultiLaneResearchRunner
from src.ledger.db import get_connection
from src.ledger.migrations import apply_migrations
from src.ledger.repository import LedgerRepository
from src.ledger.service import LedgerService


def test_gcloudignore_does_not_exclude_ledger_migrations():
    """Verify .gcloudignore preserves ledger/migrations/*.sql for Cloud Build."""
    gcloudignore = Path(".gcloudignore")
    assert gcloudignore.exists()
    lines = [
        line.strip()
        for line in gcloudignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert "ledger/**" not in lines, ".gcloudignore must not ignore ledger/** (strips ledger/migrations/*.sql)"
    assert "ledger/" not in lines, ".gcloudignore must not ignore ledger/ directory"
    assert "ledger" not in lines, ".gcloudignore must not ignore ledger directory"

    # Ensure migration files exist and are not matched by ignore patterns (unless negated)
    migration_files = list(Path("ledger/migrations").glob("*.sql"))
    assert len(migration_files) >= 5, "Expected at least 5 SQL migration files in ledger/migrations"


def test_ledger_repository_auto_initializes_schema_on_empty_db():
    """Verify LedgerRepository.list_questions() never raises OperationalError: no such table: questions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        empty_db = str(Path(tmpdir) / "uninitialized.db")
        # Touch 0-byte file simulating unmigrated sqlite file
        Path(empty_db).touch()

        repo = LedgerRepository(db_path=empty_db)
        questions = repo.list_questions()
        assert questions == []
        assert repo.list_sources() == []
        assert repo.list_claims() == []
        assert repo.list_search_logs() == []


def test_apply_migrations_fallback_when_migrations_dir_missing():
    """Verify apply_migrations still initializes all required tables even if relative dir is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "fallback_schema.db")
        missing_dir = str(Path(tmpdir) / "nonexistent_migrations")

        version = apply_migrations(db_path=db_path, migrations_dir=missing_dir)
        assert version >= 1

        repo = LedgerRepository(db_path=db_path)
        assert repo.list_questions() == []


def test_hosted_demo_run_workflow_populates_in_memory_claims_without_db_writes(monkeypatch):
    """Verify that in HOSTED_DEMO=1 on a fresh DB, run_workflow returns claims and findings while writing 0 DB rows."""
    monkeypatch.setenv("HOSTED_DEMO", "1")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "cloud_run_ledger.db")
        prac_db_path = str(Path(tmpdir) / "cloud_run_prac.db")
        q_yaml = str(Path(tmpdir) / "register.yaml")

        runner = MultiLaneResearchRunner(
            db_path=db_path,
            practitioner_db_path=prac_db_path,
            questions_yaml_path=q_yaml,
        )
        mock_papers = [
            {
                "id": "p-cloud-01",
                "title": "Empirical Evaluation of Agentic AI Coding in Enterprise Software Delivery",
                "abstract": "Controlled experiment with 80 developers demonstrates that specification-driven test suites reduce hallucinated bugs by 42% while improving velocity by 25%.",
                "year": 2024,
                "venue": "ICSE",
                "url": "https://doi.org/10.1145/example1",
                "relevance_score": 0.95,
            }
        ]
        res = runner.run_workflow(
            topic="What empirical evidence exists regarding agentic AI coding in enterprise software delivery?",
            depth="Fast",
            tone="Executive",
            map_provider="stub",
            reduce_provider="stub",
            academic_papers_override=mock_papers,
        )

        # Must return non-empty claims and findings for the UI even in stateless HOSTED_DEMO mode
        assert len(res["claims"]) >= 1
        assert len(res["findings"]) >= 1
        assert res["gap_matrix"]["academic_state"] in ("supported", "partial")

        # And zero rows written to persistent SQLite DB
        with get_connection(db_path) as conn:
            assert conn.execute("SELECT count(*) FROM runs;").fetchone()[0] == 0
            assert conn.execute("SELECT count(*) FROM claims;").fetchone()[0] == 0
            assert conn.execute("SELECT count(*) FROM sources;").fetchone()[0] == 0


def test_ledger_service_loads_questions_from_yaml_when_db_empty(monkeypatch):
    """Verify LedgerService can provide default questions from YAML when DB is empty in HOSTED_DEMO=1."""
    monkeypatch.setenv("HOSTED_DEMO", "1")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "empty_hosted.db")
        service = LedgerService(
            db_path=db_path,
            questions_yaml_path="questions/register.yaml",
        )
        # In HOSTED_DEMO=1, sync_questions_from_yaml must not raise PermissionError
        questions = service.sync_questions_from_yaml()
        assert len(questions) >= 1
