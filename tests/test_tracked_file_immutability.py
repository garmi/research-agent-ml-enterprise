"""Test verifying tracked-file immutability across the repository (Slice S0 Task 3).

Guarantees that test executions never mutate, pollute, or delete ANY tracked file in git.
Tests must execute against isolated temporary directories (tmp_path / tempfile)
and never write directly to tracked repository paths.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional
import pytest


def test_no_tracked_file_mutations_across_entire_repo(
    tracked_files_session_snapshot: Dict[str, Optional[str]],
    current_tracked_files_snapshot: Callable[[], Dict[str, Optional[str]]],
):
    """Fail if ANY tracked file across the repository was modified during test run.

    Compares the current content-based sha256 hash of every tracked file against
    the session-start snapshot, catching modifications, deletions, or corruptions.
    Zero imports from conftest; relies strictly on pytest fixture injection.
    """
    start_snapshot = tracked_files_session_snapshot
    current_snapshot = current_tracked_files_snapshot()

    mutations = []
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

    assert not mutations, (
        f"Tracked repository files were modified during test execution: {mutations}\n"
        f"Tests must use isolated temporary paths and avoid mutating ANY tracked file."
    )
