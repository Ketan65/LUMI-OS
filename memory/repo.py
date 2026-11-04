"""MemoryRepo — single door for all memory ops (session + store + facts + backup)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

from memory import store


class MemoryRepo:
    def __init__(self, config: dict | None = None):
        mem_cfg = (config or {}).get("memory", {})
        self.db_path = Path(mem_cfg.get("db_path", store.DEFAULT_DB))
        self.backup_dir = Path(mem_cfg.get("backup_dir", store.BACKUP_DIR))
        self.keep = int(mem_cfg.get("keep_backups", store.KEEP_BACKUPS))
        self.history_limit = int(mem_cfg.get("history_limit", 20))
        store.init_db(self.db_path)
        self.session_id = uuid4().hex[:12]  # fresh id per run, old data untouched

    def load_history_for_llm(self, limit: int | None = None) -> list[dict]:
        """Last N messages as chat dicts — seeds context after restart."""
        rows = store.get_recent(limit or self.history_limit, db_path=self.db_path)
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    def save_both(self, role: str, content: str) -> None:
        """Persist one message in the current session (append-only)."""
        try:
            store.save_message(self.session_id, role, content, db_path=self.db_path)
        except (sqlite3.Error, OSError) as exc:
            raise RuntimeError(f"Memory write fail: {exc}") from None

    def recent(self, limit: int = 10) -> list[dict]:
        return store.get_recent(limit, db_path=self.db_path)

    # ── Long-term facts ───────────────────────────────────────────────────────
    def remember(self, key: str, value: str, category: str = "general") -> None:
        store.save_fact(key, value, category, db_path=self.db_path)

    def recall(self, query: str, limit: int = 5) -> list[dict]:
        return store.search_facts(query, limit, db_path=self.db_path)

    def search_conversations(self, query: str, limit: int = 5) -> list[dict]:
        return store.search_conversations(query, limit, db_path=self.db_path)

    def search_memory(self, query: str, limit: int = 5) -> dict:
        """Unified memory search returning both matching facts and past conversation turns."""
        return {
            "facts": self.recall(query, limit=limit),
            "conversations": self.search_conversations(query, limit=limit),
        }

    def forget(self, key_or_id: str | int) -> bool:
        return store.delete_fact(key_or_id, db_path=self.db_path)

    def list_facts(self, category: str = "") -> list[dict]:
        return store.get_facts(category=category, active_only=True, db_path=self.db_path)

    def load_facts_for_prompt(self, limit: int = 10) -> list[str]:
        facts = store.get_facts(active_only=True, db_path=self.db_path)[:limit]
        return [f"{f['key']}: {f['value']}" for f in facts]

    def count_facts(self) -> int:
        return store.count_facts(db_path=self.db_path)

    # ── Session & Backups ─────────────────────────────────────────────────────
    def new_session(self) -> str:
        self.session_id = uuid4().hex[:12]
        return self.session_id

    def startup_backup(self) -> Path:
        return store.backup_db(self.db_path, self.backup_dir, self.keep)

    def journal_mode(self) -> str:
        return store.journal_mode(self.db_path)

    def count_messages(self) -> int:
        return store.count_messages(self.db_path)

    # ── Schedules & Reminders ─────────────────────────────────────────────────
    def save_reminder(self, text: str, trigger_time: str, kind: str = "reminder") -> str:
        sid = f"rem_{uuid4().hex[:8]}"
        store.save_schedule(sid, kind, trigger_time, text, db_path=self.db_path)
        return sid

    def list_reminders(self, status: str | None = "pending") -> list[dict]:
        return store.get_schedules(status=status, db_path=self.db_path)

    def complete_reminder(self, sid: str) -> bool:
        return store.update_schedule_status(sid, "completed", db_path=self.db_path)

    def cancel_reminder(self, sid: str) -> bool:
        return store.delete_schedule(sid, db_path=self.db_path)
