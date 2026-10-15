"""Pytest configuration and suite-wide tracked file immutability guard (Slice S0).

Guarantees that test executions never mutate, pollute, or delete any tracked files in git.
Captures content-based sha256 hashes of all files in `git ls-files` at session start
and asserts that zero tracked files were modified across the entire repository by session end.
Exposes fixtures for immutability tests without requiring imports from conftest.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional
import pytest


def _compute_file_sha256(filepath: str | Path) -> Optional[str]:
    """Return SHA-256 hex digest for a file on disk, or None if file does not exist."""
    p = Path(filepath)
    if not p.is_file():
        return None
    h = hashlib.sha256()
    try:
        with open(p, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _compute_head_sha256(filepath: str) -> Optional[str]:
    """Return SHA-256 hex digest for a file at HEAD in git, or None if not committed."""
    res = subprocess.run(["git", "show", f"HEAD:{filepath}"], capture_output=True)
    if res.returncode != 0:
        return None
    return hashlib.sha256(res.stdout).hexdigest()


def _get_tracked_files_snapshot() -> Dict[str, Optional[str]]:
    """Return dict of relative_path -> sha256 digest for every file in `git ls-files` on disk."""
    res = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    snapshot: Dict[str, Optional[str]] = {}
    for line in res.stdout.splitlines():
        path = line.strip()
        if path:
            snapshot[path] = _compute_file_sha256(path)
    return snapshot


def _get_baseline_tracked_snapshot() -> Dict[str, Optional[str]]:
    """Return dict of relative_path -> sha256 digest for every file in `git ls-files` at HEAD baseline."""
    res = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    snapshot: Dict[str, Optional[str]] = {}
    for line in res.stdout.splitlines():
        path = line.strip()
        if path:
            snapshot[path] = _compute_head_sha256(path)
    return snapshot


_SESSION_START_SNAPSHOT: Dict[str, Optional[str]] = {}


def pytest_sessionstart(session: pytest.Session) -> None:
    """Snapshot content-based sha256 hashes of all tracked files before tests run."""
    global _SESSION_START_SNAPSHOT
    _SESSION_START_SNAPSHOT = _get_tracked_files_snapshot()


def compare_tracked_snapshots(
    start_snapshot: Dict[str, Optional[str]],
    current_snapshot: Dict[str, Optional[str]],
) -> List[str]:
    """Pure function comparing two tracked file snapshots.

    Returns a list of mutation descriptors (empty if snapshots are identical).
    """
    mutations: List[str] = []
    for path, start_hash in start_snapshot.items():
        curr_hash = current_snapshot.get(path)
        if curr_hash != start_hash:
            if curr_hash is None:
                mutations.append(f"DELETED {path}")
            elif start_hash is None:
                mutations.append(f"RESTORED {path}")
            else:
                mutations.append(f"MODIFIED {path}")

    for path in current_snapshot:
        if path not in start_snapshot:
            mutations.append(f"NEW_TRACKED {path}")

    return mutations


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Assert that zero tracked files across the repository changed content during the run."""
    current_snapshot = _get_tracked_files_snapshot()
    mutations = compare_tracked_snapshots(_SESSION_START_SNAPSHOT, current_snapshot)

    if mutations:
        session.exitstatus = 1
        sys.stderr.write(
            f"\n[IMMUTABILITY VIOLATION] Test execution mutated tracked repository files:\n"
            + "\n".join(f"  - {m}" for m in mutations)
            + "\nTests must use isolated temporary paths (tmp_path / tempfile) and avoid mutating tracked files.\n"
        )


@pytest.fixture(scope="session")
def tracked_files_session_snapshot() -> Dict[str, Optional[str]]:
    """Session-scoped fixture holding the start-of-session snapshot of tracked files."""
    if _SESSION_START_SNAPSHOT is None:
        raise RuntimeError("Session-start tracked files snapshot was not initialized.")
    return dict(_SESSION_START_SNAPSHOT)


@pytest.fixture
def current_tracked_files_snapshot() -> Callable[[], Dict[str, Optional[str]]]:
    """Fixture returning a callable that takes the current snapshot of tracked files."""
    return _get_tracked_files_snapshot


@pytest.fixture
def snapshot_comparator() -> Callable[[Dict[str, Optional[str]], Dict[str, Optional[str]]], List[str]]:
    """Fixture returning pure comparison function for snapshots."""
    return compare_tracked_snapshots

