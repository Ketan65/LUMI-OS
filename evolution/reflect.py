"""Reflect — read-only LLM call se lesson nikal kar journal me save (tools NAHI).
Evolution loop ka MVP: ACT(turned) -> REFLECT(yahan) -> STORE(journal) -> INJECT."""

from __future__ import annotations

import json

REFLECT_PROMPT = """Tu LUMI ka reflection reviewer hai. Neeche ek user turn ka
summary hai. Ek experience se EK chhota lesson nikal jo AGLE session me galti
dohrai se bachaye (ya jo accha chala usse repeat karo).
Rules: sirf STRICT JSON do (aur kuch nahi); lesson Hinglish me <=25 words;
improve_next = concrete action; severity: none=sab theek, minor=chhoti
improvement, major=kaam galat hua ya user ko dikkat hui.
JSON format:
{"what_worked": ["..."], "what_failed": ["..."], "lesson": "...",
 "improve_next": "...", "severity": "none"}"""

TRIVIAL_HINTS = ("hi", "hello", "hey", "bye", "ok", "okay", "thanks", "thank you",
                 "kaise ho", "kya haal", "chalo", "hmm")


def build_reflection_input(turn: dict) -> str | None:
    """Turn summary + TRIVIAL filter — greeting/1-line chitchat = skip (cost)."""
    user = str(turn.get("user") or "").strip()
    reply = str(turn.get("reply") or "").strip()
    tools = list(turn.get("tools") or [])
    retries = int(turn.get("retries") or 0)
    low = user.lower()
    if not tools and not retries and (len(user.split()) <= 6
                                      or any(h in low for h in TRIVIAL_HINTS)):
        return None                              # trivial = bina LLM call ke skip
    return "\n".join([
        f"trigger: {turn.get('trigger', 'manual')}",
        f"user ask: {user[:300]}",
        f"tools chale: {', '.join(str(t) for t in tools) if tools else 'koi nahi'}",
        f"errors/retries: {retries}",
        f"final reply (excerpt): {reply[:250]}",
    ])


def _parse(text: str) -> dict | None:
    """Pehla JSON object nikalo (prose/trailing ignore) + keys validate."""
    start = (text or "").find("{")
    if start == -1:
        return None
    try:
        blob, _ = json.JSONDecoder().raw_decode(text[start:])
    except ValueError:
        return None
    if not isinstance(blob, dict) or "lesson" not in blob:
        return None
    sev = str(blob.get("severity") or "none").lower()
    if sev not in {"none", "minor", "major"}:
        sev = "none"

    def _lst(key: str) -> list[str]:
        v = blob.get(key)
        if isinstance(v, list):
            return [str(x)[:120] for x in v[:6]]
        return [str(v)[:120]] if v else []

    return {"what_worked": _lst("what_worked"), "what_failed": _lst("what_failed"),
            "lesson": str(blob.get("lesson"))[:300],
            "improve_next": str(blob.get("improve_next") or "")[:300],
            "severity": sev}


def run(brain, turn: dict, journal, session_id: str = "") -> dict | None:
    """LLM reflect (temperature 0.3, read-only) -> journal save. Crash = ZERO."""
    body = build_reflection_input(turn)
    if body is None:
        return None                               # trivial — LLM call hi nahi
    messages = [{"role": "user", "content": REFLECT_PROMPT + "\n\n" + body}]
    entry = None
    try:
        reply = brain.chat(messages, tools=None, temperature=0.3)
        entry = _parse(reply.text or "")
        if entry is None:                         # parse fail -> 1 retry (reminder)
            messages += [{"role": "assistant", "content": reply.text or ""},
                         {"role": "user", "content":
                          "JSON ONLY — upar diye gaye STRICT JSON format me do."}]
            reply = brain.chat(messages, tools=None, temperature=0.3)
            entry = _parse(reply.text or "")
    except Exception:                             # noqa: BLE001 — crash ZERO
        entry = None
    if entry is None:                             # dono baar fail -> honest entry
        entry = {"what_worked": [], "what_failed": ["LLM se valid JSON nahi aaya"],
                 "lesson": "(parse failed)", "improve_next": "next turn pe retry",
                 "severity": "none"}
    entry["trigger"] = str(turn.get("trigger") or "manual")
    entry["session_id"] = session_id or str(turn.get("session_id") or "")
    try:
        journal.save(entry)
        print(f"📝 reflected [{entry['trigger']}] {entry['severity']}: "
              f"{entry['lesson'][:90]}")
        try:                                    # auto-propose (skills, Task O)
            from evolution.skills import propose_skill
            propose_skill({**entry, "tools": turn.get("tools") or []}, brain)
        except Exception:                       # noqa: BLE001 — propose fail = skip
            pass
    except Exception:                             # noqa: BLE001 — save fail = no crash
        return None
    return entry
