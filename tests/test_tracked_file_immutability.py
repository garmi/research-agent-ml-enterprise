"""Test verifying tracked-file immutability across the repository (Slice S0 & S1).

Guarantees that test executions never mutate, pollute, or delete ANY tracked file in git.
Tests must execute against isolated temporary directories (tmp_path / tempfile)
and never write directly to tracked repository paths.
Includes unit tests for pure comparison function (unchanged, pre-modified unchanged,
pre-modified changed further, deleted, new tracked).
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional
import pytest


def test_no_tracked_file_mutations_across_entire_repo(
    tracked_files_session_snapshot: Dict[str, Optional[str]],
    current_tracked_files_snapshot: Callable[[], Dict[str, Optional[str]]],
    snapshot_comparator: Callable[[Dict[str, Optional[str]], Dict[str, Optional[str]]], List[str]],
):
    """Fail if ANY tracked file across the repository was modified during test run.

    Compares the current content-based sha256 hash of every tracked file against
    the session-start snapshot, catching modifications, deletions, or corruptions.
    Zero imports from conftest; relies strictly on pytest fixture injection.
    """
    start_snapshot = tracked_files_session_snapshot
    current_snapshot = current_tracked_files_snapshot()
    mutations = snapshot_comparator(start_snapshot, current_snapshot)

    assert not mutations, (
        f"Tracked repository files were modified during test execution: {mutations}\n"
        f"Tests must use isolated temporary paths and avoid mutating ANY tracked file."
    )


# ==============================================================================
# Pure Snapshot Comparison Unit Tests (Slice S1 Task 6)
# ==============================================================================

def test_compare_tracked_snapshots_unchanged(
    snapshot_comparator: Callable[[Dict[str, Optional[str]], Dict[str, Optional[str]]], List[str]],
):
    """Snapshots with identical file hashes produce zero mutations."""
    start = {"src/engine/entry.py": "hash_a", "web_app.py": "hash_b"}
    current = {"src/engine/entry.py": "hash_a", "web_app.py": "hash_b"}
    mutations = snapshot_comparator(start, current)
    assert mutations == []


def test_compare_tracked_snapshots_pre_modified_file_unchanged(
    snapshot_comparator: Callable[[Dict[str, Optional[str]], Dict[str, Optional[str]]], List[str]],
):
    """A file modified before the session that does not change during tests produces no violation."""
    # start_snapshot records the working tree hash on disk at session start (which may differ from HEAD)
    start = {"web_app.py": "hash_working_copy_v1"}
    # at session finish, the file still has the exact same working copy hash
    current = {"web_app.py": "hash_working_copy_v1"}
    mutations = snapshot_comparator(start, current)
    assert mutations == []


def test_compare_tracked_snapshots_pre_modified_file_changed_further(
    snapshot_comparator: Callable[[Dict[str, Optional[str]], Dict[str, Optional[str]]], List[str]],
):
    """A file modified before the session that changes further during tests must be caught."""
    start = {"web_app.py": "hash_working_copy_v1"}
    current = {"web_app.py": "hash_working_copy_v2_dirty"}
    mutations = snapshot_comparator(start, current)
    assert mutations == ["MODIFIED web_app.py"]


def test_compare_tracked_snapshots_deleted_file(
    snapshot_comparator: Callable[[Dict[str, Optional[str]], Dict[str, Optional[str]]], List[str]],
):
    """A tracked file deleted during testing is flagged as DELETED."""
    start = {"tracked_doc.md": "hash_doc"}
    # File missing from disk or mapped to None
    current_none = {"tracked_doc.md": None}
    assert snapshot_comparator(start, current_none) == ["DELETED tracked_doc.md"]

    current_missing = {}
    assert snapshot_comparator(start, current_missing) == ["DELETED tracked_doc.md"]


def test_compare_tracked_snapshots_new_tracked_file(
    snapshot_comparator: Callable[[Dict[str, Optional[str]], Dict[str, Optional[str]]], List[str]],
):
    """A new file added to tracked files during testing is flagged as NEW_TRACKED."""
    start = {"existing.py": "hash_exist"}
    current = {"existing.py": "hash_exist", "new_leak.py": "hash_leak"}
    mutations = snapshot_comparator(start, current)
    assert mutations == ["NEW_TRACKED new_leak.py"]
