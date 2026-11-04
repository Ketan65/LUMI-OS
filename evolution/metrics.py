"""Metrics — evolution report card (DB read-only, INSTANT, 0 LLM) + manual judge.
LLM judge SIRF /evolution judge se (cost control) — auto kabhi nahi."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import date, timedelta

JUDGE_PROMPT = """Tu LUMI ka lesson JUDGE hai. Neeche reflections hain — har
ek ko score karo, LESSON ko basis maan (improve_next second). Basis:
useful = lesson MEIN specific detail hai (kya kiya/kaise) aur agli baar apply ho sake;
generic = bina detail ke directive ya platitude ("same approach use karo", "sahi
chala", "jawab dena") — chaahe kaam successful ho, ye generic hai;
bad = galat, empty ya bekaar.
Sirf STRICT JSON, aur kuch nahi:
{"scores": [{"id": 1, "score": "useful"}, {"id": 2, "score": "generic"}]}
score values: useful | generic | bad"""


def evolution_report(db_path, skills_list: list[dict]) -> dict:
    """Sab kuch SQL/file read se — 0 LLM calls. CLI card + /api/evolution isi se."""
    out = {"reflections": {"total": 0, "today": 0, "by_severity": {}},
           "lessons": {"applied": 0, "pending": 0},
           "skills": {"active": 0, "candidate": 0, "retired": 0,
                      "avg_success_pct": 0, "needs_review": []},
           "tools_health": {"success_pct_7d": 0, "retry_rate_7d": 0,
                            "error_rate_7d": 0},
           "judge": {"scored": 0, "useful": 0, "generic": 0, "bad": 0}}
    try:
        with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True,
                                     timeout=10)) as conn:
            total, applied = conn.execute(
                "SELECT COUNT(*), SUM(applied) FROM reflections").fetchone()
            out["reflections"]["total"] = int(total or 0)
            out["lessons"]["applied"] = int(applied or 0)
            out["lessons"]["pending"] = out["reflections"]["total"] - out["lessons"]["applied"]
            today = date.today().isoformat()
            out["reflections"]["today"] = conn.execute(
                "SELECT COUNT(*) FROM reflections WHERE ts LIKE ?",
                (today + "%",)).fetchone()[0]
            for sev, n in conn.execute(
                    "SELECT COALESCE(severity,'none'), COUNT(*)"
                    " FROM reflections GROUP BY severity"):
                out["reflections"]["by_severity"][str(sev)] = n
            cutoff = (date.today() - timedelta(days=6)).isoformat()
            n, good, retried, errs = conn.execute(
                "SELECT COUNT(*), SUM(decision IN ('auto','ask_yes')),"
                " SUM(retry_used), SUM(decision='error') FROM tool_calls"
                " WHERE ts >= ? AND decision IS NOT NULL", (cutoff,)).fetchone()
            if n:
                out["tools_health"] = {
                    "success_pct_7d": round(100.0 * (good or 0) / n, 1),
                    "retry_rate_7d": round(100.0 * (retried or 0) / n, 1),
                    "error_rate_7d": round(100.0 * (errs or 0) / n, 1)}
            j = conn.execute(
                "SELECT COUNT(judge_score), SUM(judge_score='useful'),"
                " SUM(judge_score='generic'), SUM(judge_score='bad')"
                " FROM reflections").fetchone()
            out["judge"] = {"scored": int(j[0] or 0), "useful": int(j[1] or 0),
                            "generic": int(j[2] or 0), "bad": int(j[3] or 0)}
    except sqlite3.Error:
        pass                                   # zeros > crash (DB locked/gone)
    pct: list[float] = []
    for s in skills_list or []:                # YAML files = caller se (reuse)
        st = str(s.get("status") or "candidate")
        if st in ("active", "candidate", "retired"):
            out["skills"][st] += 1
        uses, ok = int(s.get("uses") or 0), int(s.get("successes") or 0)
        if uses > 0:
            p = 100.0 * ok / uses
            pct.append(p)
            if uses >= 4 and p < 50:           # flag ONLY — retire user ka kaam
                out["skills"]["needs_review"].append(str(s.get("name")))
    out["skills"]["avg_success_pct"] = round(sum(pct) / len(pct)) if pct else 0
    return out


def judge_unjudged(brain, journal, cap: int = 10) -> str:
    """MANUAL command (/evolution judge) — batch score, save. Parse fail = bad."""
    rows = journal.unjudged(cap)
    if not rows:
        return "Sab reflections already judged hain. ✅"
    lines = [f"[id={r['id']}] ({r['severity']}) lesson: {r['lesson']}"
             f" -> improve: {r['improve_next'] or '-'}" for r in rows]
    scores: dict[int, str] = {}
    try:
        reply = brain.chat([{"role": "user",
                             "content": JUDGE_PROMPT + "\n\n" + "\n".join(lines)}],
                           tools=None, temperature=0.2)
        text = reply.text or ""
        start = text.find("{")
        if start != -1:
            blob, _ = json.JSONDecoder().raw_decode(text[start:])
            for item in (blob.get("scores") or []):
                if isinstance(item, dict) and item.get("id") is not None:
                    scores[int(item["id"])] = str(item.get("score") or "").lower()
    except Exception:                          # noqa: BLE001 — fail = all bad
        scores = {}
    counts = {"useful": 0, "generic": 0, "bad": 0}
    for r in rows:
        sc = scores.get(r["id"], "bad")        # missing/parse-fail = bad (exit pool)
        if sc not in counts:
            sc = "bad"
        journal.set_judge(r["id"], sc)
        counts[sc] += 1
    msg = (f"⚖️ judged {len(rows)} oldest unjudged: {counts['useful']} useful / "
           f"{counts['generic']} generic / {counts['bad']} bad")
    print(msg)
    return msg


def report_text(d: dict) -> str:
    """Formatted card (CLI /evolution) — sirf dict se, koi call nahi."""
    r, l, s, t, j = (d["reflections"], d["lessons"], d["skills"],
                     d["tools_health"], d["judge"])
    sev = " / ".join(f"{k} {v}" for k, v in sorted(r["by_severity"].items())) or "-"
    needs = (f" · {len(s['needs_review'])} needs_review ⚠ "
             f"({', '.join(s['needs_review'])})") if s["needs_review"] else ""
    judge_line = (f"Judge: {j['useful']} useful / {j['generic']} generic / "
                  f"{j['bad']} bad")
    if j["scored"] < r["total"]:
        judge_line += "  (run: /evolution judge)"
    return "\n".join([
        "LUMI EVOLUTION REPORT ─────────────",
        f"Reflections: {r['total']} (aj {r['today']}) · severity: {sev}",
        f"Lessons injected: {l['applied']}/{r['total']}",
        f"Skills: {s['active']} active (avg {s['avg_success_pct']}%) · "
        f"{s['candidate']} candidate · {s['retired']} retired{needs}",
        f"Tools 7d: {t['success_pct_7d']}% success · {t['retry_rate_7d']}% retry · "
        f"{t['error_rate_7d']}% error",
        judge_line,
        "────────────────────────────────────"])
