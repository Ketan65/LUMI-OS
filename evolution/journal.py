"""Journal — append-only reflections table (lumi.db, evolution ka STORE)."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import date, datetime

_SCHEMA = """CREATE TABLE IF NOT EXISTS reflections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    session_id TEXT,
    trigger TEXT,
    what_worked TEXT,
    what_failed TEXT,
    lesson TEXT,
    improve_next TEXT,
    severity TEXT,
    applied INTEGER DEFAULT 0
)"""


class Journal:
    """Har op me fresh connection (background-thread se safe), fail = honest zero."""

    def __init__(self, db_path):
        self.db_path = str(db_path)
        self._init()

    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        try:
            with closing(self._conn()) as conn, conn:
                conn.execute(_SCHEMA)
                cols = [r[1] for r in conn.execute("PRAGMA table_info(reflections)")]
                if "judge_score" not in cols:      # Task P migration (null|useful|generic|bad)
                    conn.execute("ALTER TABLE reflections ADD COLUMN judge_score TEXT")
        except sqlite3.Error:
            pass                               # init fail = last_n() empty, no crash

    def unjudged(self, limit: int = 10) -> list[dict]:
        """Oldest unjudged rows (judge ke liye — cap default 10)."""
        try:
            with closing(self._conn()) as conn:
                rows = conn.execute(
                    "SELECT id, ts, trigger, lesson, improve_next, severity"
                    " FROM reflections WHERE judge_score IS NULL"
                    " ORDER BY id ASC LIMIT ?", (int(limit),)).fetchall()
        except sqlite3.Error:
            return []
        return [dict(r) for r in rows]

    def set_judge(self, entry_id: int, score: str) -> None:
        if score not in {"useful", "generic", "bad"}:
            score = "bad"
        try:
            with closing(self._conn()) as conn, conn:
                conn.execute("UPDATE reflections SET judge_score=? WHERE id=?",
                             (score, int(entry_id)))
        except sqlite3.Error:
            pass

    def save(self, entry: dict) -> int:
        with closing(self._conn()) as conn, conn:
            cur = conn.execute(
                "INSERT INTO reflections (ts, session_id, trigger, what_worked,"
                " what_failed, lesson, improve_next, severity, applied)"
                " VALUES (?,?,?,?,?,?,?,?,0)",
                (datetime.now().isoformat(timespec="seconds"),
                 str(entry.get("session_id") or ""),
                 str(entry.get("trigger") or "manual"),
                 json.dumps(entry.get("what_worked") or [], ensure_ascii=False),
                 json.dumps(entry.get("what_failed") or [], ensure_ascii=False),
                 str(entry.get("lesson") or ""),
                 str(entry.get("improve_next") or ""),
                 str(entry.get("severity") or "none")))
            return int(cur.lastrowid)

    def last_n(self, limit: int = 10) -> list[dict]:
        try:
            with closing(self._conn()) as conn:
                rows = conn.execute(
                    "SELECT * FROM reflections ORDER BY id DESC LIMIT ?",
                    (int(limit),)).fetchall()
        except sqlite3.Error:
            return []
        out = []
        for r in rows:
            d = dict(r)
            for k in ("what_worked", "what_failed"):      # JSON text -> list
                try:
                    d[k] = json.loads(d.get(k) or "[]")
                except ValueError:
                    d[k] = []
            out.append(d)
        return out

    def count_today(self) -> int:
        try:
            with closing(self._conn()) as conn:
                return conn.execute(
                    "SELECT COUNT(*) FROM reflections WHERE ts LIKE ?",
                    (date.today().isoformat() + "%",)).fetchone()[0]
        except sqlite3.Error:
            return 0

    def mark_applied(self, ids: list[int]) -> None:
        if not ids:
            return
        try:
            with closing(self._conn()) as conn, conn:
                conn.executemany(
                    "UPDATE reflections SET applied=1 WHERE id=?", [(i,) for i in ids])
        except sqlite3.Error:
            pass


def load_lessons(db_path, limit: int = 5, max_words: int = 150) -> list[str]:
    """INJECT ke liye last N lessons — 'lesson -> improve', total <= max_words.
    Jo rows inject hui unhe applied=1 mark kar dete hain."""
    jrn = Journal(db_path)
    entries = jrn.last_n(limit)
    out: list[str] = []
    ids: list[int] = []
    used = 0
    for e in reversed(entries):                # oldest-first (chronological order)
        lesson = str(e.get("lesson") or "").strip()
        if not lesson:
            continue
        text = lesson + (f" -> {e['improve_next']}" if e.get("improve_next") else "")
        w = len(text.split())
        if used + w > max_words:
            break
        out.append(text)
        ids.append(int(e.get("id") or 0))
        used += w
    jrn.mark_applied(ids)
    return out
