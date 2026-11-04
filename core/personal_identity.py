"""Personal Identity — LUMI ke liye user profile, preferences aur context.

Prioritizes git-ignored `config/identity.local.json` for private local personalization,
and falls back to generic `config/identity.json` template so zero PII is ever committed to Git.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

LOCAL_IDENTITY_PATH = Path("config/identity.local.json")
IDENTITY_PATH = Path("config/identity.json")


def load_identity() -> dict[str, Any]:
    """Loads private `config/identity.local.json` if present, else `config/identity.json`."""
    for candidate in (LOCAL_IDENTITY_PATH, IDENTITY_PATH):
        if candidate.exists():
            try:
                with candidate.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
    return _default_identity()


def _default_identity() -> dict[str, Any]:
    return {
        "user": {
            "name": "Commander",
            "call_name": "Boss",
            "handle": "Operator",
            "role": "owner",
            "language": "hinglish",
            "personality": "jarvis",
        },
        "preferences": {
            "voice_voice": "af_heart",
            "wake_word": "hey lumi",
            "auto_speak": False,
            "proactive": True,
        },
        "context": {
            "location": "India",
            "timezone": "Asia/Kolkata",
            "work_hours": [9, 18],
        },
        "devices": {
            "pc": "NVIDIA RTX Workstation",
            "node_id": "node_workstation_primary",
        },
        "projects": [],
        "memory": {
            "favorite_apps": ["chrome", "vscode"],
            "ongoing_projects": [],
            "notes": [],
        },
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def save_identity(identity: dict[str, Any]) -> None:
    target = LOCAL_IDENTITY_PATH if LOCAL_IDENTITY_PATH.exists() else IDENTITY_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        json.dump(identity, f, indent=2, ensure_ascii=False)


def get_user_name(identity: dict[str, Any] | None = None) -> str:
    ident = identity or load_identity()
    user = ident.get("user", {})
    return user.get("call_name") or user.get("name") or "Boss"


def get_full_name(identity: dict[str, Any] | None = None) -> str:
    ident = identity or load_identity()
    return ident.get("user", {}).get("name") or "Commander"


def get_language(identity: dict[str, Any] | None = None) -> str:
    ident = identity or load_identity()
    return ident.get("user", {}).get("language", "hinglish")


def is_proactive(identity: dict[str, Any] | None = None) -> bool:
    ident = identity or load_identity()
    return ident.get("preferences", {}).get("proactive", True)


def build_identity_prompt_block() -> str:
    """Dynamically builds the operator profile block for LLM system prompts from local identity."""
    ident = load_identity()
    u = ident.get("user", {})
    name = u.get("name", "Commander")
    handle = u.get("handle", "Operator")
    college = u.get("college", "")
    internship = u.get("internship", "")
    pc = ident.get("devices", {}).get("pc", "Local GPU Workstation")
    projects = ident.get("projects", [])
    proj_str = ", ".join(f"{p.get('name')} ({p.get('desc', '')[:60]})" for p in projects[:6] if isinstance(p, dict))

    lines = [f"- Master User: **{name}** (Handle: **{handle}**)."]
    if college:
        lines.append(f"- Academic / Research Base: {college}.")
    if internship:
        lines.append(f"- Security & Operations Context: {internship}.")
    if proj_str:
        lines.append(f"- Flagship Projects: {proj_str}.")
    lines.append(f"- Hardware: {pc} running LUMI Sovereign OS.")
    return "\n".join(lines)
