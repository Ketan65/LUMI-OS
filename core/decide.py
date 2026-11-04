"""Decision Engine (Task Z2) — /decide <situation> → values.yaml pe faisla.
Contract: EXACT output format (⚖/📌/✅/🔄/⚠), rule CITE = values ke exact
lines, hard-rule conflict bole. LLM fail → friendly, crash ZERO."""

from __future__ import annotations

import time
from pathlib import Path

from core import values as V

LOG = Path("data/logs/brain.log")

SYSTEM = """Tum LUMI ho — USER ki values.yaml rules neeche. Diye gaye SITUATION pe faisla do — Hinglish, ~120 words, EXACTLY iss format me:
⚖ DECISION: <1 line action>
📌 KYUN: <reasoning — rule ka TEXT quote karke>
✅ RULES APPLIED: <bullet list — values ke exact lines>
🔄 ALTERNATIVES: <1-2 consider kiye, kyun reject>
⚠ CONFLICT: hard_rules se takraye toh 'HARD RULE: <line>' + 'YE NAHI KARUNGA'; warna 'koi conflict nahi'
Fake/number mat ghadho. Values me hai wahi cite karo.

EXAMPLE:
SITUATION: aaj gym jaun ya nahi
⚖ DECISION: Haan jao — 30 min walk aaj complete kar do.
📌 KYUN: Tumhari rule hai "Roz kam se kam 30 min walk" — aaj wo pending hai.
✅ RULES APPLIED:
- Roz kam se kam 30 min walk
🔄 ALTERNATIVES: Ghar pe aaram — reject kyunki walk daily rule hai.
⚠ CONFLICT: koi conflict nahi"""

FALLBACK = "faisla abhi nahi ban paaya, dobara bolo"
USAGE = ("/decide <situation> — values pe faisla\n"
         "usage: /decide aaj gym jaun ya nahi")


def _log(msg: str) -> None:
    try:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} decide {msg}\n")
    except OSError:
        pass


def _facts(memory) -> str:
    """Light user context — last 3 real user messages (fake facts ZERO)."""
    if not memory:
        return ""
    try:
        rows = [m for m in memory.recent(30)
                if str(m.get("role")) == "user"][-3:]
        return "\n".join(f"- {str(m.get('content'))[:80]}" for m in rows)
    except Exception:                             # noqa: BLE001 — optional
        return ""


def decide(situation: str, brain, memory=None) -> str:
    """SITUATION → values pe structured faisla (format contract upar).
    Empty → usage; values missing → auto-recreate + note; LLM fail → friendly."""
    situation = (situation or "").strip()
    if not situation:
        return USAGE
    note = ""
    if not V.values_path().exists():
        V.ensure_file()
        note = "\n(default template — apni rules values.yaml me daalo)"
    facts = _facts(memory)
    user = (f"USER VALUES (values.yaml):\n{V.flatten_for_prompt()}\n\n"
            + (f"FACTS (recent, light context):\n{facts}\n\n" if facts else "")
            + f"SITUATION: {situation}")
    t0 = time.time()
    try:
        reply = brain.chat([{"role": "system", "content": SYSTEM},
                            {"role": "user", "content": user}],
                           tools=None, temperature=0.3)
        text = (getattr(reply, "text", "") or "").strip()
    except Exception as exc:                      # noqa: BLE001 — friendly
        _log(f"llm fail: {type(exc).__name__}")
        text = ""
    if not text:
        return FALLBACK + note
    _log(f"ok ms={int((time.time() - t0) * 1000)} chars={len(text)}")
    return text + note
