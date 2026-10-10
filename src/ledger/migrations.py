"""Forward-only schema migration and durability engine for Research Engine v2.

Mandatory durability requirements:
1. schema_version tracking in `meta` table.
2. Forward-only migrations from `ledger/migrations/`.
3. Automatic timestamped backup before every migration and bulk write.
4. Retention of last N backups.
5. SQLite WAL mode and integrity checks.
"""

from __future__ import annotations

import datetime
import glob
import logging
import os
import re
import shutil
import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple

from src.ledger.db import get_connection

logger = logging.getLogger(__name__)

DEFAULT_MIGRATIONS_DIR = "ledger/migrations"
DEFAULT_BACKUPS_DIR = "ledger/backups"


def create_backup(
    db_path: str,
    backups_dir: str = DEFAULT_BACKUPS_DIR,
    keep_last_n: int = 10,
    prefix: str = "backup",
) -> Optional[str]:
    """Create a timestamped backup of the database before migrations or bulk writes.

    Rotates older backups to keep the last `keep_last_n`.
    """
    source = Path(db_path)
    if not source.exists() or source.stat().st_size == 0:
        return None

    target_dir = Path(backups_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_filename = f"{prefix}_{source.stem}_{timestamp}.db"
    backup_path = target_dir / backup_filename

    # SQLite VACUUM INTO is the cleanest online backup, or shutil.copy2
    try:
        conn = sqlite3.connect(str(source))
        conn.execute(f"VACUUM INTO '{backup_path.resolve()}';")
        conn.close()
    except Exception:
        # Fallback to copy2 if VACUUM INTO fails (e.g. older sqlite)
        shutil.copy2(source, backup_path)

    # Rotate old backups
    pattern = str(target_dir / f"{prefix}_{source.stem}_*.db")
    existing_backups = sorted(glob.glob(pattern))
    if len(existing_backups) > keep_last_n:
        for old_backup in existing_backups[:-keep_last_n]:
            try:
                os.remove(old_backup)
            except OSError:
                pass

    return str(backup_path)


def get_current_schema_version(conn: sqlite3.Connection) -> int:
    """Return the current schema version from the meta table, or 0 if uninitialized."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meta';")
        if not cursor.fetchone():
            return 0
        cursor.execute("SELECT MAX(schema_version) FROM meta;")
        row = cursor.fetchone()
        if row and row[0] is not None:
            return int(row[0])
        return 0
    except sqlite3.Error:
        return 0


def list_migration_files(migrations_dir: str = DEFAULT_MIGRATIONS_DIR) -> List[Tuple[int, Path]]:
    """List and sort migration sql files by version prefix (e.g. 001_initial_schema.sql -> 1)."""
    dir_path = Path(migrations_dir)
    if not dir_path.exists():
        return []

    migrations: List[Tuple[int, Path]] = []
    pattern = re.compile(r"^(\d+)_.+\.sql$")
    for file_path in dir_path.glob("*.sql"):
        match = pattern.match(file_path.name)
        if match:
            version = int(match.group(1))
            migrations.append((version, file_path))

    migrations.sort(key=lambda x: x[0])
    return migrations


def apply_migrations(
    db_path: str,
    migrations_dir: str = DEFAULT_MIGRATIONS_DIR,
    backups_dir: str = DEFAULT_BACKUPS_DIR,
    keep_last_n: int = 10,
) -> int:
    """Apply all pending forward migrations to the target database.

    Creates an automatic timestamped backup prior to applying any new migration.

    Returns:
        The latest schema version after migrations.
    """
    conn = get_connection(db_path, verify_integrity=False)
    current_version = get_current_schema_version(conn)
    all_migrations = list_migration_files(migrations_dir)

    pending = [m for m in all_migrations if m[0] > current_version]
    if not pending:
        conn.close()
        return current_version

    # Perform backup before modifying schema
    conn.close()
    create_backup(db_path, backups_dir=backups_dir, keep_last_n=keep_last_n, prefix="pre_migration")

    conn = get_connection(db_path, verify_integrity=True)
    try:
        for version, migration_file in pending:
            logger.info("Applying migration %03d from %s", version, migration_file.name)
            with open(migration_file, "r", encoding="utf-8") as f:
                sql_script = f.read()

            conn.executescript(sql_script)

            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO meta (schema_version, created_at) VALUES (?, ?);",
                (version, now_iso),
            )
            conn.commit()
            current_version = version

        return current_version
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Migration failed at version {version}: {e}") from e
    finally:
        conn.close()
