"""Analytics builder — DB COUNTs + brain.log parse (corrupt line = SKIP, no crash)."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path


def build_analytics(db_path, log_path: str = "data/logs/brain.log",
                    days: int = 7) -> dict:
    """Single JSON for /api/analytics — sab real, empty/corrupt pe honest zeros."""
    days = max(1, min(int(days), 30))
    today = date.today()
    t = today.isoformat()
    out: dict = {
        "today": {"messages": 0, "tool_calls": 0, "sessions": 0,
                  "tool_success_pct": 100.0},
        "latency": {"avg_ms_today": 0, "avg_ms_7d": 0, "max_ms_today": 0},
        "providers": [], "fallbacks_today": 0, "tools_top": [],
        "daily": [], "_skipped_lines": 0,
    }

    # ---- DB: conversations + tool_calls (COUNT queries, ro mode) ----
    if db_path:
        conn = None
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            out["today"]["messages"] = conn.execute(
                "SELECT COUNT(*) FROM conversations WHERE ts LIKE ?",
                (t + "%",)).fetchone()[0]
            out["today"]["tool_calls"] = conn.execute(
                "SELECT COUNT(*) FROM tool_calls WHERE ts LIKE ?",
                (t + "%",)).fetchone()[0]
            out["today"]["sessions"] = conn.execute(
                "SELECT COUNT(DISTINCT session_id) FROM conversations "
                "WHERE ts LIKE ?", (t + "%",)).fetchone()[0]
            rows = conn.execute(
                "SELECT decision, COUNT(*) FROM tool_calls WHERE ts LIKE ? "
                "GROUP BY decision", (t + "%",)).fetchall()
            total = sum(r[1] for r in rows)
            good = sum(r[1] for r in rows if r[0] in {"auto", "ask_yes"})
            if total:
                out["today"]["tool_success_pct"] = round(100.0 * good / total, 1)
            for tool, cnt, auto, yes, err in conn.execute(
                    "SELECT tool, COUNT(*), SUM(decision='auto'), "
                    "SUM(decision='ask_yes'), SUM(decision='error') "
                    "FROM tool_calls GROUP BY tool ORDER BY COUNT(*) DESC LIMIT 6"):
                out["tools_top"].append(
                    {"tool": tool, "count": cnt, "auto": int(auto or 0),
                     "ask_yes": int(yes or 0), "ask_no": 0, "block": 0,
                     "error": int(err or 0)})
            msgs = dict(conn.execute(
                "SELECT substr(ts,1,10), COUNT(*) FROM conversations GROUP BY 1"))
            tools = dict(conn.execute(
                "SELECT substr(ts,1,10), COUNT(*) FROM tool_calls GROUP BY 1"))
            for i in range(days - 1, -1, -1):          # zero-filled honest days
                d = (today - timedelta(days=i)).isoformat()
                out["daily"].append({"date": d, "messages": int(msgs.get(d, 0)),
                                     "tools": int(tools.get(d, 0))})
        except sqlite3.Error:
            pass                                       # zeros > crash
        finally:
            if conn:
                conn.close()

    # ---- brain.log: latency + providers + fallbacks (defensive) ----
    lp = Path(log_path)
    skipped = 0
    agg: dict[str, list[int]] = {}                     # prov -> [calls, ms_sum, err]
    ms_today: list[int] = []
    ms_7d: list[int] = []
    max_today = 0
    cutoff = (today - timedelta(days=6)).isoformat()
    if lp.exists():
        try:
            lines = lp.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            lines = []
        for line in lines:
            try:
                parts = line.split()
                datetime.fromisoformat(parts[0])       # validate timestamp
                if len(parts) > 1 and parts[1] == "WARN":
                    continue                           # context-warning = not corrupt
                d = parts[0][:10]
                if "FALLBACK" in line:
                    if d == t:
                        out["fallbacks_today"] += 1
                    continue
                prov = ms = None
                err = False
                for p in parts[1:]:
                    if p.startswith("provider="):
                        prov = p.split("=", 1)[1]
                    elif p.startswith("ms="):
                        ms = int(p.split("=", 1)[1])
                    elif p == "err":
                        err = True
                if prov is None or ms is None:
                    raise ValueError("fields missing")
                slot = agg.setdefault(prov, [0, 0, 0])
                slot[0] += 1
                slot[1] += ms
                slot[2] += 1 if err else 0
                if not err:
                    if d == t:
                        ms_today.append(ms)
                        max_today = max(max_today, ms)
                    if d >= cutoff:
                        ms_7d.append(ms)
            except Exception:                          # noqa: BLE001 — skip, count
                skipped += 1
    out["_skipped_lines"] = skipped
    out["providers"] = [
        {"name": k, "calls": v[0],
         "avg_ms": round(v[1] / v[0]) if v[0] else 0, "errors": v[2]}
        for k, v in agg.items()]
    out["latency"] = {
        "avg_ms_today": round(sum(ms_today) / len(ms_today)) if ms_today else 0,
        "avg_ms_7d": round(sum(ms_7d) / len(ms_7d)) if ms_7d else 0,
        "max_ms_today": max_today}
    return out
