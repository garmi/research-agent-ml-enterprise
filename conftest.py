"""Pytest configuration and session-finish immutability guard (Slice S0).

Guarantees that test executions never mutate, pollute, or delete any tracked files in git.
Captures tracked-file state at session start and asserts that zero tracked files were
modified across the entire repository by session end.
"""

from __future__ import annotations

import subprocess
import sys
import pytest

_SESSION_START_TRACKED_STATUS: dict[str, str] = {}


def _get_tracked_status() -> dict[str, str]:
    res = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
    )
    tracked = {}
    for raw_line in res.stdout.splitlines():
        if not raw_line.strip() or raw_line.startswith("??"):
            continue
        parts = raw_line.strip().split(maxsplit=1)
        if len(parts) == 2:
            status, path = parts
            tracked[path] = status
    return tracked


def get_session_start_status() -> dict[str, str]:
    """Return a copy of the tracked files status captured at session start."""
    return dict(_SESSION_START_TRACKED_STATUS)


def pytest_sessionstart(session: pytest.Session) -> None:
    """Snapshot the git status of all tracked files before tests run."""
    _SESSION_START_TRACKED_STATUS.clear()
    _SESSION_START_TRACKED_STATUS.update(_get_tracked_status())


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Assert that zero tracked files across the repository were modified during the run."""
    current_tracked = _get_tracked_status()

    mutations = []
    # Check for newly modified or staged tracked files
    for path, status in current_tracked.items():
        if path not in _SESSION_START_TRACKED_STATUS or _SESSION_START_TRACKED_STATUS[path] != status:
            mutations.append(f"{status} {path}")

    # Check for tracked files that were reverted or deleted
    for path, status in _SESSION_START_TRACKED_STATUS.items():
        if path not in current_tracked:
            mutations.append(f"REVERTED/REMOVED {path}")

    if mutations:
        session.exitstatus = 1
        sys.stderr.write(
            f"\n[IMMUTABILITY VIOLATION] Test execution mutated tracked repository files:\n"
            + "\n".join(f"  - {m}" for m in mutations)
            + "\nTests must use isolated temporary paths (tmp_path / tempfile) and avoid mutating tracked files.\n"
        )
