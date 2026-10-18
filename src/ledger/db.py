"""Database connection and lifecycle manager for Research Engine v2.

Enforces:
- SQLite WAL mode (PRAGMA journal_mode=WAL;)
- Foreign key constraints (PRAGMA foreign_keys=ON;)
- Integrity verification on startup (PRAGMA integrity_check;)
- Isolated paths for ledger.db vs practitioner.db
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_LEDGER_PATH = "ledger/ledger.db"
DEFAULT_PRACTITIONER_PATH = "ledger/practitioner.db"


def default_ledger_path() -> str:
    """Ledger database path: RESEARCH_LEDGER_DB when set, otherwise DEFAULT_LEDGER_PATH.

    Read at call time so a process (or the test sandbox) can redirect the default.
    """
    return os.getenv("RESEARCH_LEDGER_DB") or DEFAULT_LEDGER_PATH


def default_practitioner_path() -> str:
    """Practitioner database path: RESEARCH_PRACTITIONER_DB when set, otherwise DEFAULT_PRACTITIONER_PATH."""
    return os.getenv("RESEARCH_PRACTITIONER_DB") or DEFAULT_PRACTITIONER_PATH


def init_db_directory(db_path: str) -> None:
    """Ensure parent directory exists."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)


def get_connection(
    db_path: Optional[str] = None,
    verify_integrity: bool = True,
) -> sqlite3.Connection:
    """Open and configure a SQLite connection with durability pragmas.

    Args:
        db_path: Path to SQLite database file. Defaults to default_ledger_path().
        verify_integrity: Whether to run PRAGMA integrity_check on connection.

    Returns:
        Configured sqlite3.Connection with Row factory and WAL mode.
    """
    target_path = db_path or default_ledger_path()
    init_db_directory(target_path)

    conn = sqlite3.connect(target_path, timeout=30.0)
    conn.row_factory = sqlite3.Row

    # Enforce durability pragmas
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    if verify_integrity:
        cursor = conn.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError(
                f"Database integrity check failed for {target_path}: {result[0] if result else 'unknown'}"
            )

    return conn
