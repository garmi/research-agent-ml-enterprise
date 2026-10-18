"""Default runtime paths honour RESEARCH_* overrides, so a test run never writes into the checkout.

The autouse fixture in the root conftest.py points every default ledger, outputs, backups and
approvals location at the test's tmp_path. These tests pin the resolution rules that make that work.
"""

from __future__ import annotations

from pathlib import Path


def test_default_paths_fall_back_to_repo_layout_without_overrides(monkeypatch):
    from src.ledger.db import DEFAULT_LEDGER_PATH, DEFAULT_PRACTITIONER_PATH
    from src.ledger.db import default_ledger_path, default_practitioner_path

    monkeypatch.delenv("RESEARCH_LEDGER_DB", raising=False)
    monkeypatch.delenv("RESEARCH_PRACTITIONER_DB", raising=False)

    assert DEFAULT_LEDGER_PATH == "ledger/ledger.db"
    assert DEFAULT_PRACTITIONER_PATH == "ledger/practitioner.db"
    assert default_ledger_path() == "ledger/ledger.db"
    assert default_practitioner_path() == "ledger/practitioner.db"


def test_default_paths_follow_environment_overrides(tmp_path, monkeypatch):
    from src.ledger.db import default_ledger_path, default_practitioner_path

    monkeypatch.setenv("RESEARCH_LEDGER_DB", str(tmp_path / "x.db"))
    monkeypatch.setenv("RESEARCH_PRACTITIONER_DB", str(tmp_path / "y.db"))

    assert default_ledger_path() == str(tmp_path / "x.db")
    assert default_practitioner_path() == str(tmp_path / "y.db")


def test_suite_sandbox_covers_every_runtime_location(tmp_path):
    from src.engine.approvals import get_approvals_dir
    from src.ledger.db import default_ledger_path, default_practitioner_path
    from src.ledger.migrations import default_backups_dir
    from src.config import default_outputs_dir

    root = tmp_path
    assert Path(default_ledger_path()).is_relative_to(root)
    assert Path(default_practitioner_path()).is_relative_to(root)
    assert Path(default_backups_dir()).is_relative_to(root)
    assert Path(get_approvals_dir()).is_relative_to(root)
    assert Path(default_outputs_dir()).is_relative_to(root)


def test_default_constructed_services_write_only_inside_sandbox(tmp_path):
    from src.analysis.multilane_runner import MultiLaneResearchRunner
    from src.ledger.service import LedgerService
    from src.publish.publisher import Publisher

    root = tmp_path

    runner = MultiLaneResearchRunner()
    service = LedgerService()
    publisher = Publisher()

    assert Path(runner.db_path).is_relative_to(root)
    assert Path(runner.practitioner_db_path).is_relative_to(root)
    assert Path(runner.questions_yaml_path).is_relative_to(root)
    assert Path(service.db_path).is_relative_to(root)
    assert Path(publisher.db_path).is_relative_to(root)
    assert Path(publisher.export_dir).is_relative_to(root)

    # The default databases were created in the sandbox, not in the repo's ledger/ directory.
    assert Path(runner.db_path).exists()
    assert Path(runner.practitioner_db_path).exists()
