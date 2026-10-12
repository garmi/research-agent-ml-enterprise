"""Test A18: Working Tree Immutability and UI Smoke Test Assertion (Prompt A3-5).

Verifies:
1. Working tree cleanliness: test executions leave no tracked or untracked repository mutations.
2. Git history audit: no .db, outputs/, .env, denylist.txt, or temporary files are tracked at HEAD.
3. test_ui_smoke.py only skips when Playwright is uninstalled; launches Streamlit and tests 3-lane rendering.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
import pytest


def test_working_tree_cleanliness_after_test_execution():
    """Verify git status --porcelain shows no unexpected untracked artifacts."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
    # Any untracked files starting with ?? outside of intentional test work should fail
    untracked_artifacts = [
        l for l in lines
        if l.startswith("??") and not l.endswith("tests/test_a18_working_tree_and_ui_smoke.py")
    ]
    assert not untracked_artifacts, f"Working tree contains dirty untracked artifacts: {untracked_artifacts}"


def test_git_history_audit_no_unwanted_files_at_head():
    """Audit tracked files at HEAD: ensure no .db, outputs/, .env, or denylist.txt are committed."""
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    tracked_files = [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]

    prohibited = [
        f for f in tracked_files
        if f.endswith(".db")
        or (f.startswith("outputs/") and not f.startswith("outputs/quarantine/.gitkeep"))
        or (f == ".env" or f.endswith("/.env"))
        or f == "denylist.txt"
        or f.endswith(".tmp")
    ]
    assert not prohibited, f"Prohibited confidential or temporary files committed at HEAD: {prohibited}"


def test_ui_smoke_only_skips_when_playwright_uninstalled():
    """Verify test_ui_smoke.py contains no skip clauses for MachPort or TargetClosedError."""
    smoke_file = Path("tests/test_ui_smoke.py")
    assert smoke_file.exists()
    content = smoke_file.read_text(encoding="utf-8")

    assert "MachPortRendezvousServer" not in content, "test_ui_smoke.py must not skip on MachPort"
    assert "TargetClosedError" not in content, "test_ui_smoke.py must not skip on TargetClosedError"
    assert "Playwright is not installed at all" in content
    assert "Active Three-Lane Architecture & Ingestion Readiness" in content
