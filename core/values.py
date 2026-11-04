"""Values file (Task Z1) — USER ki zindagi ki rules: values.yaml (project root).
Yeh USER ki file hai: tolerant parsing (junk = warn, crash ZERO), validate-BEFORE-
write + .bak backup. Template = Hinglish EXAMPLES (user edit karega).
Z2 (decision engine) isi pe faisa lega — flatten_for_prompt se prompt me jayega."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "values.yaml"
BAK = ROOT / "values.yaml.bak"
LOG = ROOT / "data" / "logs" / "brain.log"
KNOWN = ("health", "money", "time", "goals", "hard_rules", "communication")

TEMPLATE = """# LUMI ke liye MERI rules — edit karte raho, LUMI isi pe faisa lega
version: 1

health:
  wake_time: "05:30"
  sleep_by: "23:00"
  rules:
    - "Roz kam se kam 30 min walk"
    - "Junk food hafte me max 1 baar"

money:
  monthly_budget: 50000
  rules:
    - "Subscription lene se pehle pucha karo"
    - "Crypto monthly cap: sirf 5000 rupees"

time:
  rules:
    - "09:00-12:00 deep work — beech me disturb mat karo"

goals:
  - name: "LUMI v1 complete"
    deadline: "2026-12-31"

hard_rules:            # HAMESHA inhe follow — priority sabse upar
  - "Password/OTP kabhi mat poochhna"
  - "Raat 2 baje ke baad koi naya kaam start mat karna"

communication:
  language: "Hinglish"
  reply_style: "seedha, motivate karne wala, emoji kam"
"""


def _log(msg: str) -> None:
    try:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} values {msg}\n")
    except OSError:
        pass


def values_path() -> Path:
    return FILE


def ensure_file() -> bool:
    """Missing -> template se create (log '[values] created'). True = naya bana."""
    if FILE.exists():
        return False
    FILE.write_text(TEMPLATE, encoding="utf-8")
    _log("created template")
    print("[values] created (template)")
    return True


def load_values() -> dict:
    """yaml.safe_load; not-a-dict (junk) -> {} + log — crash ZERO."""
    ensure_file()
    try:
        data = yaml.safe_load(FILE.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        _log(f"load error: {type(exc).__name__}")
        return {}
    if not isinstance(data, dict):
        _log("load: top-level not dict -> {}")
        return {}
    return data


def flatten_for_prompt(max_words: int = 450) -> str:
    """Rules ko ek prompt-string me (Z2-ready). ORDER: hard_rules -> goals ->
    health/money/time -> communication. Word cap enforced."""
    v = load_values()
    lines: list[str] = []
    for r in _as_strs(v.get("hard_rules")):
        lines.append(f"HARD: {r}")
    goals = v.get("goals")
    if isinstance(goals, list):
        for g in goals:
            if isinstance(g, dict) and g.get("name"):
                dl = f" (deadline {g.get('deadline')})" if g.get("deadline") else ""
                lines.append(f"GOAL: {g['name']}{dl}")
    for cat in ("health", "money", "time"):
        c = v.get(cat) if isinstance(v.get(cat), dict) else {}
        for key in ("wake_time", "sleep_by", "monthly_budget"):
            if c.get(key) not in (None, ""):
                lines.append(f"RULE: {cat}.{key} = {c[key]}")
        for r in _as_strs(c.get("rules")):
            lines.append(f"RULE: {r}")
    comm = v.get("communication") if isinstance(v.get("communication"), dict) else {}
    if comm:
        lines.append("COMM: " + ", ".join(f"{k}={x}" for k, x in comm.items()))
    words = " ".join(lines).split()
    if len(words) > max_words:
        out: list[str] = []
        used = 0
        for ln in lines:                         # poore line rakho, cap words pe
            w = len(ln.split())
            if used + w > max_words:
                out.append("...(aur rules values.yaml me)")
                break
            out.append(ln)
            used += w
        return "\n".join(out)
    return "\n".join(lines)


def _as_strs(val) -> list[str]:
    if isinstance(val, list):
        return [str(x) for x in val if str(x).strip()]
    return []


def validate(content: str) -> tuple[bool, list, list]:
    """(ok, errors, warnings) — errors = save block karte hain, warnings = OK.
    Friendly lines, crash ZERO."""
    errors: list[str] = []
    warn: list[str] = []
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        if mark is not None:                     # yaml ne line number diya
            errors.append(f"line {mark.line + 1} me indentation theek karo — "
                          f"{getattr(exc, 'problem', 'yaml problem')}")
        else:
            errors.append(f"YAML problem — {exc}")
        return (False, errors, warn)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        errors.append("Top-level dict hona chahiye (jaise: health:, money:, ...)")
        return (False, errors, warn)
    for k in data:                                # junk keys = warning only
        if k not in KNOWN and k != "version":
            warn.append(f"'{k}' naam samajh nahi aaya (ignore ho jayega)")
    for cat in KNOWN:                             # empty categories = warning
        if cat not in data or not data.get(cat):
            warn.append(f"{cat} khaali hai — edit me add kar sakte ho")
    if "hard_rules" in data and not _as_strs(data.get("hard_rules")):
        warn.append("hard_rules me kuch nahi — priority rules empty hain")
    return (True, errors, warn)


def save_values(content: str) -> tuple[bool, list, list]:
    """Validate BEFORE write -> current -> values.yaml.bak -> write -> log.
    Returns (ok, errors, warnings). File unchanged jab validate fail ho."""
    ok, errors, warn = validate(content)
    if not ok:
        _log(f"save rejected ({len(errors)} errors)")
        return (False, errors, warn)
    try:
        ensure_file()
        shutil.copyfile(FILE, BAK)                # overwrite .bak = pehle wali
        FILE.write_text(content, encoding="utf-8")
    except OSError as exc:
        return (False, [f"File write nahi hui — {exc}"], warn)
    _log(f"saved ({len(content)} bytes, {len(warn)} warnings)")
    return (True, errors, warn)


def counts(data: dict) -> dict:
    """parsed dict se rule counts (badge 'N rules loaded' ke liye)."""
    def rules_of(x) -> int:
        if isinstance(x, dict):
            x = x.get("rules")
        return len(_as_strs(x))
    goals = data.get("goals") if isinstance(data.get("goals"), list) else []
    c = {
        "hard_rules": len(_as_strs(data.get("hard_rules"))),
        "health": rules_of(data.get("health")),
        "money": rules_of(data.get("money")),
        "time": rules_of(data.get("time")),
        "goals": sum(1 for g in goals if isinstance(g, dict) and g.get("name")),
    }
    c["total"] = sum(c.values())
    return c
