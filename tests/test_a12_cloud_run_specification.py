"""Test verification for Cloud Run hardening specification (Prompt A2-7).

Ensures:
- Service name is executive-research-engine in asia-south1 (not research-agent in us-central1)
- Uses --update-env-vars (never destructive --set-env-vars)
- No Cloud Storage FUSE volume mount for SQLite (stateless demo mode)
- Includes --max-instances cap
- Includes Google Cloud budget alert command
- Uses operator-configurable IAM group variable
- Integrity report explicitly details reversibility for every command
"""

import os
from pathlib import Path
import pytest

HARDENING_SCRIPT = Path("scripts/cloud_run_hardening.sh")
REPORT_PATH = Path("INTEGRITY_REPORT.md")


def test_hardening_script_service_and_region():
    assert HARDENING_SCRIPT.exists(), f"Expected {HARDENING_SCRIPT} to exist."
    content = HARDENING_SCRIPT.read_text(encoding="utf-8")
    assert "executive-research-engine" in content
    assert "asia-south1" in content
    assert "us-central1" not in content
    assert "research-agent" not in content.replace("executive-research-engine", "")


def test_hardening_script_safe_env_vars():
    content = HARDENING_SCRIPT.read_text(encoding="utf-8")
    assert "--update-env-vars" in content
    assert "--set-env-vars" not in content


def test_hardening_script_no_fuse_sqlite_mount():
    content = HARDENING_SCRIPT.read_text(encoding="utf-8")
    assert "cloud-storage" not in content
    assert "--add-volume" not in content
    assert "--add-volume-mount" not in content
    assert "HOSTED_DEMO=1" in content


def test_hardening_script_max_instances_and_budget_alert():
    content = HARDENING_SCRIPT.read_text(encoding="utf-8")
    assert "--max-instances" in content
    assert "gcloud billing budgets create" in content


def test_hardening_script_configurable_iam_group():
    content = HARDENING_SCRIPT.read_text(encoding="utf-8")
    assert "AUTHORIZED_INVOKER_GROUP" in content
    assert "authorized-researchers@enterprise.com" not in content


def test_integrity_report_documents_reversibility():
    report_text = REPORT_PATH.read_text(encoding="utf-8")
    assert "A2-7" in report_text or "Section A2-7" in report_text
    assert "Reversible" in report_text
    assert "executive-research-engine" in report_text
    assert "asia-south1" in report_text
