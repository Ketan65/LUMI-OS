"""SQLite Multi-Thread Guard — High-Concurrency WAL Engine & Zero-Locking Provider.

Hardens SQLite databases across LUMI (lumi.db, vault.db, audit.db):
  - Enforces WAL (Write-Ahead Logging) mode.
  - Sets PRAGMA busy_timeout = 5000ms (engine-level busy waiting before throwing errors).
  - Configures PRAGMA synchronous = NORMAL for high-speed durability.
  - Provides retry_sqlite_transaction for multi-thread race protection.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Callable


def open_hardened_sqlite(db_path: Path | str, timeout: float = 30.0) -> sqlite3.Connection:
    """Opens a SQLite connection hardened against Windows multi-thread file locking."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path, timeout=max(5.0, float(timeout)))
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA cache_size = -64000;")  # 64MB memory page cache
    return conn


def retry_sqlite_transaction(
    fn: Callable[[], Any],
    max_retries: int = 5,
    base_delay: float = 0.05,
) -> Any:
    """Executes a database operation with exponential backoff on lock contention."""
    last_exc = None
    for attempt in range(max_retries):
        try:
            return fn()
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                last_exc = exc
                time.sleep(base_delay * (2 ** attempt))
                continue
            raise
    if last_exc:
        raise last_exc
