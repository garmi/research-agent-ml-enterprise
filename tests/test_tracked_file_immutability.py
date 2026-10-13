"""Test verifying tracked-file immutability across the repository (Slice S0 Task 3).

Guarantees that test executions never mutate, pollute, or delete ANY tracked file in git.
Tests must execute against isolated temporary directories (tmp_path / tempfile)
and never write directly to tracked repository paths.
"""

from __future__ import annotations

import pytest
from conftest import _get_tracked_status, get_session_start_status


def test_no_tracked_file_mutations_across_entire_repo():
    """Fail if ANY tracked file across the repository was modified during test run.

    Verifies against session-start state that zero tracked files in the repository
    (code, config, schemas, templates, data files) were mutated by tests.
    Contains no hard-coded allowlist.
    """
    session_start_status = get_session_start_status()
    current_tracked = _get_tracked_status()

    mutations = []
    for path, status in current_tracked.items():
        if path not in session_start_status or session_start_status[path] != status:
            mutations.append(f"{status} {path}")

    for path, status in session_start_status.items():
        if path not in current_tracked:
            mutations.append(f"REVERTED/REMOVED {path}")

    assert not mutations, (
        f"Tracked repository files were modified during test execution: {mutations}\n"
        f"Tests must use isolated temporary paths and avoid mutating ANY tracked file."
    )
