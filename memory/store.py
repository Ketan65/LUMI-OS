"""SQLite persistence — conversations, facts, append-only history, WAL crash-safe."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

DEFAULT_DB = Path("data") / "lumi.db"
BACKUP_DIR = Path("data") / "backups"
KEEP_BACKUPS = 7


def _connect(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")   # crash safety: writes don't corrupt on kill
    conn.execute("PRAGMA synchronous=NORMAL")  # speed + WAL = still durable enough
    return conn


def init_db(db_path: Path = DEFAULT_DB) -> Path:
    with _connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS conversations (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   ts TEXT NOT NULL,
                   session_id TEXT NOT NULL,
                   role TEXT NOT NULL,
                   content TEXT NOT NULL
               )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS facts (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   ts TEXT NOT NULL,
                   key TEXT NOT NULL UNIQUE,
                   value TEXT NOT NULL,
                   category TEXT DEFAULT 'general',
                   active INTEGER DEFAULT 1
               )"""
        )
        # migrations if older table was created without category or active
        cur = conn.execute("PRAGMA table_info(facts)")
        cols = {row[1] for row in cur.fetchall()}
        if "category" not in cols:
            conn.execute("ALTER TABLE facts ADD COLUMN category TEXT DEFAULT 'general'")
        if "active" not in cols:
            conn.execute("ALTER TABLE facts ADD COLUMN active INTEGER DEFAULT 1")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS schedules (
                   id TEXT PRIMARY KEY,
                   kind TEXT NOT NULL,
                   trigger_time TEXT NOT NULL,
                   payload TEXT NOT NULL,
                   created_at TEXT NOT NULL,
                   status TEXT DEFAULT 'pending'
               )"""
        )
    return db_path


def journal_mode(db_path: Path = DEFAULT_DB) -> str:
    with _connect(db_path) as conn:
        return str(conn.execute("PRAGMA journal_mode").fetchone()[0])


def save_message(session_id: str, role: str, content: str,
                 db_path: Path = DEFAULT_DB) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO conversations (ts, session_id, role, content) VALUES (?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), session_id, role, content),
        )


def get_recent(limit: int = 20, session_id: str | None = None,
               db_path: Path = DEFAULT_DB) -> list[dict]:
    sql = "SELECT ts, session_id, role, content FROM conversations"
    params: tuple = ()
    if session_id:
        sql += " WHERE session_id = ?"
        params = (session_id,)
    sql += " ORDER BY id DESC LIMIT ?"
    with _connect(db_path) as conn:
        rows = conn.execute(sql, params + (limit,)).fetchall()
    rows.reverse()  # oldest first — LLM needs chronological order
    return [dict(zip(("ts", "session_id", "role", "content"), r)) for r in rows]


def count_messages(db_path: Path = DEFAULT_DB) -> int:
    with _connect(db_path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0])


def search_conversations(query: str, limit: int = 5, db_path: Path = DEFAULT_DB) -> list[dict]:
    """Search past conversation history by keyword + Hybrid RRF across all sessions."""
    term = f"%{query.strip().lower()}%"
    sql = "SELECT id, ts, session_id, role, content FROM conversations WHERE lower(content) LIKE ? ORDER BY id DESC LIMIT ?"
    with _connect(db_path) as conn:
        rows = conn.execute(sql, (term, limit)).fetchall()
    exact_matches = [dict(zip(("id", "ts", "session_id", "role", "content"), r)) for r in rows]
    if len(exact_matches) >= limit:
        return exact_matches[:limit]
    try:
        from core.hybrid_retriever import HybridRRFEngine
        with _connect(db_path) as conn:
            all_rows = conn.execute(
                "SELECT id, ts, session_id, role, content FROM conversations ORDER BY id DESC LIMIT 250"
            ).fetchall()
        docs = [dict(zip(("id", "ts", "session_id", "role", "content"), r)) for r in all_rows]
        ranked = HybridRRFEngine().rank_documents(query, docs, text_key="content", top_k=limit)
        seen_ids = {m["id"] for m in exact_matches}
        for d in ranked:
            if d["id"] not in seen_ids and (d.get("bm25_score", 0.0) > 0.0 or d.get("vector_score", 0.0) >= 0.15):
                clean = {k: d[k] for k in ("id", "ts", "session_id", "role", "content") if k in d}
                exact_matches.append(clean)
                seen_ids.add(d["id"])
                if len(exact_matches) >= limit:
                    break
    except Exception:
        pass
    return exact_matches[:limit]



# ── Long-term memory (facts) ──────────────────────────────────────────────────
def save_fact(key: str, value: str, category: str = "general",
              db_path: Path = DEFAULT_DB) -> None:
    """Upsert a fact (user preference, identity, project rule)."""
    ts = datetime.now().isoformat(timespec="seconds")
    with _connect(db_path) as conn:
        conn.execute(
            """INSERT INTO facts (ts, key, value, category, active)
               VALUES (?, ?, ?, ?, 1)
               ON CONFLICT(key) DO UPDATE SET
                   value = excluded.value,
                   category = excluded.category,
                   ts = excluded.ts,
                   active = 1""",
            (ts, key.strip().lower(), value.strip(), (category or "general").strip().lower())
        )


def get_facts(category: str | None = None, active_only: bool = True,
              db_path: Path = DEFAULT_DB) -> list[dict]:
    sql = "SELECT id, ts, key, value, category, active FROM facts WHERE 1=1"
    params: list = []
    if active_only:
        sql += " AND active = 1"
    if category:
        sql += " AND category = ?"
        params.append(category.strip().lower())
    sql += " ORDER BY id ASC"
    with _connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(zip(("id", "ts", "key", "value", "category", "active"), r)) for r in rows]


def search_facts(query: str, limit: int = 5, db_path: Path = DEFAULT_DB) -> list[dict]:
    """Keyword + Hybrid RRF search across keys, values, and categories."""
    term = f"%{query.strip().lower()}%"
    with _connect(db_path) as conn:
        rows = conn.execute(
            """SELECT id, ts, key, value, category, active FROM facts
               WHERE active = 1 AND (key LIKE ? OR value LIKE ? OR category LIKE ?)
               ORDER BY id DESC LIMIT ?""",
            (term, term, term, limit)
        ).fetchall()
    exact_matches = [dict(zip(("id", "ts", "key", "value", "category", "active"), r)) for r in rows]
    if len(exact_matches) >= limit:
        return exact_matches[:limit]
    try:
        from core.hybrid_retriever import HybridRRFEngine
        all_facts = get_facts(active_only=True, db_path=db_path)
        for f in all_facts:
            f["_composite"] = f"{f['key']} {f['value']} {f['category']}"
        ranked = HybridRRFEngine().rank_documents(query, all_facts, text_key="_composite", top_k=limit)
        seen_ids = {m["id"] for m in exact_matches}
        for d in ranked:
            if d["id"] not in seen_ids and (d.get("bm25_score", 0.0) > 0.0 or d.get("vector_score", 0.0) >= 0.15):
                clean = {k: d[k] for k in ("id", "ts", "key", "value", "category", "active") if k in d}
                exact_matches.append(clean)
                seen_ids.add(d["id"])
                if len(exact_matches) >= limit:
                    break
    except Exception:
        pass
    return exact_matches[:limit]


def delete_fact(key_or_id: str | int, db_path: Path = DEFAULT_DB) -> bool:
    """Soft-delete a fact (active = 0)."""
    with _connect(db_path) as conn:
        if str(key_or_id).isdigit():
            cur = conn.execute("UPDATE facts SET active = 0 WHERE id = ?", (int(key_or_id),))
        else:
            cur = conn.execute("UPDATE facts SET active = 0 WHERE key = ?", (str(key_or_id).strip().lower(),))
        return cur.rowcount > 0


def count_facts(db_path: Path = DEFAULT_DB) -> int:
    with _connect(db_path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM facts WHERE active = 1").fetchone()[0])


# ── Schedules & Reminders ───────────────────────────────────────────────────
def save_schedule(sid: str, kind: str, trigger_time: str, payload: str,
                  db_path: Path = DEFAULT_DB) -> None:
    now_iso = datetime.now().isoformat(timespec="seconds")
    with _connect(db_path) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO schedules (id, kind, trigger_time, payload, created_at, status)
               VALUES (?, ?, ?, ?, ?, 'pending')""",
            (sid, kind, trigger_time, payload, now_iso),
        )


def get_schedules(status: str | None = None, db_path: Path = DEFAULT_DB) -> list[dict]:
    sql = "SELECT id, kind, trigger_time, payload, created_at, status FROM schedules"
    params: tuple = ()
    if status:
        sql += " WHERE status = ?"
        params = (status,)
    sql += " ORDER BY trigger_time ASC"
    with _connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
        return [
            {
                "id": r[0],
                "kind": r[1],
                "trigger_time": r[2],
                "payload": r[3],
                "created_at": r[4],
                "status": r[5],
            }
            for r in rows
        ]


def update_schedule_status(sid: str, status: str, db_path: Path = DEFAULT_DB) -> bool:
    with _connect(db_path) as conn:
        cur = conn.execute("UPDATE schedules SET status = ? WHERE id = ?", (status, sid))
        return cur.rowcount > 0


def delete_schedule(sid: str, db_path: Path = DEFAULT_DB) -> bool:
    with _connect(db_path) as conn:
        cur = conn.execute("DELETE FROM schedules WHERE id = ?", (sid,))
        return cur.rowcount > 0


# ── Backups ───────────────────────────────────────────────────────────────────
def backup_db(db_path: Path = DEFAULT_DB, backup_dir: Path = BACKUP_DIR,
              keep: int = KEEP_BACKUPS) -> Path:
    """Dated backup via sqlite backup API (WAL-aware = no lost rows)."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"lumi_{datetime.now():%Y%m%d}.db"
    with _connect(db_path) as src, sqlite3.connect(target) as dst:
        src.backup(dst)  # consistent copy even while WAL has pending writes
    # keep only the newest N backups (append-only rule does not apply to backups)
    old = sorted(backup_dir.glob("lumi_*.db"))[:-keep]
    for path in old:
        path.unlink(missing_ok=True)
    return target
