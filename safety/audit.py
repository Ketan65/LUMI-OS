"""Append-only audit trail for every tool decision (foundation for req #11)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from core.db_guard import open_hardened_sqlite


class AuditLog:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        with self._conn() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS tool_calls (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       ts TEXT NOT NULL,
                       session_id TEXT NOT NULL,
                       tool TEXT NOT NULL,
                       args_json TEXT NOT NULL,
                       decision TEXT NOT NULL,
                       result_summary TEXT NOT NULL,
                       retry_used INTEGER NOT NULL DEFAULT 0
                   )"""
            )
            try:  # migration for DBs created before the retry column existed
                conn.execute("ALTER TABLE tool_calls ADD COLUMN "
                             "retry_used INTEGER NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                pass  # column already there

    def _conn(self) -> sqlite3.Connection:
        return open_hardened_sqlite(self.db_path, timeout=30.0)

    def log(self, session_id: str, tool: str, args: dict, decision: str,
            result_summary: str, retry_used: int = 0) -> None:
        """decision ∈ {auto, ask_yes, ask_no, block, error} — append-only."""
        payload = json.dumps(args, ensure_ascii=False, default=str)
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO tool_calls (ts, session_id, tool, args_json, decision, "
                "result_summary, retry_used) VALUES (?,?,?,?,?,?,?)",
                (datetime.now().isoformat(timespec="seconds"), session_id,
                 tool, payload, decision, result_summary[:200], int(retry_used)),
            )

    def recent(self, limit: int = 5) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT ts, tool, args_json, decision, result_summary, retry_used "
                "FROM tool_calls ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(zip(("ts", "tool", "args", "decision", "summary", "retry"), r))
                for r in rows]
