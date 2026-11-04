"""Skill library — YAML recipes (procedural memory): propose/approve/inject/reuse.
Files data/skills/*.yaml — user padh/sakta hai, edit kar sakta hai (transparency)."""

from __future__ import annotations

import difflib
import json
import re
from datetime import datetime
from pathlib import Path

import yaml

from tools.registry import Tool

SKILLS_DIR = Path("data/skills")
_PROPOSALS = [0]                       # session cap: max 2 auto-proposals
STATUS_ICON = {"candidate": "🟡", "active": "🟢", "retired": "⚪"}

PROPOSE_PROMPT = """Tu LUMI ka skill crafter hai. Neeche ek successful turn ka
summary hai. Usse ek REUSABLE recipe (skill) bana jo aisi hi request pe dobara
chalaye. Sirf STRICT JSON, aur kuch nahi:
{"name": "kebab-case-name", "description": "1 line Hinglish me",
 "trigger_examples": ["jaise phir phir bologe", "..."],
 "required_tools": ["tool1", "tool2"],
 "steps": ["step 1", "step 2", "step 3"]}
Rules: name = 2-4 shabd kebab-case; steps = 3-6 concrete actions; description <=15 words."""


def _slug(name) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")


def _path(name: str) -> Path:
    return SKILLS_DIR / f"{_slug(name)}.yaml"


def save_skill(d: dict) -> tuple[bool, str]:
    """YAML file likho — fail = friendly msg, crash ZERO. Returns (ok, name|err)."""
    name = _slug(d.get("name"))
    if not name:
        return False, "Skill ka name chahiye."
    d = dict(d)
    d["name"] = name
    d.setdefault("description", "")
    d.setdefault("trigger_examples", [])
    d.setdefault("required_tools", [])
    d.setdefault("steps", [])
    d.setdefault("source_reflection", 0)
    d.setdefault("status", "candidate")
    d.setdefault("created", datetime.now().isoformat(timespec="seconds"))
    d.setdefault("last_used", "")
    d.setdefault("uses", 0)
    d.setdefault("successes", 0)
    try:
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        with open(_path(name), "w", encoding="utf-8") as f:
            yaml.safe_dump(d, f, allow_unicode=True, sort_keys=False)
        return True, name
    except (OSError, yaml.YAMLError) as exc:
        return False, f"Skill save fail: {exc}"


def list_skills(status: str | None = None) -> list[dict]:
    out: list[dict] = []
    try:
        files = sorted(SKILLS_DIR.glob("*.yaml"))
    except OSError:
        return []
    for p in files:
        try:
            d = yaml.safe_load(p.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue                          # hand-edit gadbad = us file ko skip
        if isinstance(d, dict) and d.get("name"):
            if status is None or d.get("status") == status:
                out.append(d)
    return out


def get_skill_by_name(name: str) -> dict | None:
    p = _path(name)
    if not p.exists():
        return None
    try:
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, yaml.YAMLError):
        return None


def approve(name: str) -> str:
    d = get_skill_by_name(name)
    if not d:
        return f"skill '{name}' nahi mili — /skills dekho."
    d["status"] = "active"
    ok, msg = save_skill(d)
    return (f"🟢 {d['name']} ab ACTIVE — agle session me prompt me inject hogi."
            if ok else msg)


def retire(name: str) -> str:
    d = get_skill_by_name(name)
    if not d:
        return f"skill '{name}' nahi mili — /skills dekho."
    d["status"] = "retired"
    ok, msg = save_skill(d)
    return f"⚪ {d['name']} retired — injection se gayab." if ok else msg


def mark_used(name: str, success: bool) -> None:
    """get_skill call ka use count — turn clean ho toh success bhi (+1/+1)."""
    d = get_skill_by_name(name)
    if not d:
        return
    d["uses"] = int(d.get("uses") or 0) + 1
    d["successes"] = int(d.get("successes") or 0) + (1 if success else 0)
    d["last_used"] = datetime.now().isoformat(timespec="seconds")
    save_skill(d)


def skills_text() -> str:
    rows = list_skills()
    if not rows:
        return ("Koi skill nahi — tool-task ke baad auto-propose hogi, "
                "ya /skill save se manually.")
    lines = []
    for d in rows:
        icon = STATUS_ICON.get(str(d.get("status")), "?")
        lines.append(f"{icon} {d['name']} [{d.get('status')}] — "
                     f"{d.get('description', '')} "
                     f"(uses {d.get('uses', 0)}, ok {d.get('successes', 0)})")
    return "\n".join(lines)


def _parse_skill(text: str) -> dict | None:
    """Pehla JSON object + strict validation — generic/empty = None (pollution nahi)."""
    start = (text or "").find("{")
    if start == -1:
        return None
    try:
        blob, _ = json.JSONDecoder().raw_decode(text[start:])
    except ValueError:
        return None
    if not isinstance(blob, dict):
        return None
    steps = [str(s).strip() for s in (blob.get("steps") or [])
             if isinstance(s, str) and s.strip()]
    if not _slug(blob.get("name")) or not steps:
        return None
    def lst(key: str, n: int) -> list[str]:
        v = blob.get(key)
        if not isinstance(v, list):
            return []
        return [str(x)[:80] for x in v[:n] if str(x).strip()]
    return {"name": _slug(blob.get("name")),
            "description": str(blob.get("description") or "")[:160],
            "trigger_examples": lst("trigger_examples", 5),
            "required_tools": lst("required_tools", 6),
            "steps": [s[:160] for s in steps[:8]]}


def _skills_cfg() -> dict:
    try:
        cfg = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
        return (cfg or {}).get("skills") or {}
    except (OSError, yaml.YAMLError):
        return {}


def propose_skill(ctx: dict, brain, force: bool = False) -> str:
    """Reflection/turn se candidate skill banao (auto | /skill save). Msg/"" .
    Auto: enabled+auto_propose+severity none+what_worked+tools, session cap 2."""
    cfg = _skills_cfg()
    what = [str(x).strip() for x in (ctx.get("what_worked") or []) if str(x).strip()]
    tools = [str(t) for t in (ctx.get("tools") or []) if t]
    if not force:
        if not cfg.get("enabled", True) or not cfg.get("auto_propose", True):
            return ""
        if ctx.get("severity") != "none" or not what or not tools:
            return ""
        if _PROPOSALS[0] >= int(cfg.get("max_proposals_per_session", 2)):
            return ""
    body = (f"what_worked: {'; '.join(what[:6])}\n"
            f"tools used: {', '.join(tools[:8])}\n"
            f"lesson/context: {str(ctx.get('lesson') or '')[:200]}")
    try:
        reply = brain.chat([{"role": "user",
                             "content": PROPOSE_PROMPT + "\n\n" + body}],
                           tools=None, temperature=0.3)
        d = _parse_skill(reply.text or "")
    except Exception:                          # noqa: BLE001 — LLM fail = skip
        d = None
    if not d:
        return ""                              # generic/invalid = candidate pollution nahi
    if get_skill_by_name(d["name"]):
        return f"skill '{d['name']}' pehle se hai — skip."
    d["source_reflection"] = int(ctx.get("id") or 0)
    ok, msg = save_skill(d)
    if not ok:
        return msg
    if not force:
        _PROPOSALS[0] += 1
    print(f"💡 Skill proposed: {d['name']} — /skills mein approve karo")
    return f"💡 Skill proposed: {d['name']} — /skills mein approve karo"


def get_skill(name: str) -> str:
    """TOOL handler — full YAML recipe ya not-found + closest matches."""
    d = get_skill_by_name(name)
    if d:
        return yaml.safe_dump(d, allow_unicode=True, sort_keys=False)
    names = [s["name"] for s in list_skills()]
    close = difflib.get_close_matches(str(name), names, n=3, cutoff=0.4)
    return (f"skill '{name}' nahi mili."
            + (f" Closest: {', '.join(close)}" if close else ""))


def register_skill_tool(registry) -> None:
    registry.register(Tool(
        name="get_skill",
        description="Load a saved skill recipe (full steps + tools). "
                    "KNOWN SKILLS me naam dikhe toh yahan se poori recipe lo.",
        params_schema={"type": "object",
                       "properties": {"name": {"type": "string",
                                               "description": "skill name"}},
                       "required": ["name"]},
        handler=get_skill, risk="auto"))
