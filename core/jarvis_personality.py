"""JARVIS Personality — Stark Apex Protocol (LUMI v35.0).

Provides adaptive interaction mode classification (voice_tactical, crisis_triage,
deep_engineering), Stark HUD telemetry headers, situational awareness greetings,
and context-aware response post-processing.
"""

from __future__ import annotations

import datetime
import re
from typing import Any

from core.personal_identity import load_identity

STARK_APEX_DIRECTIVES = """STARK APEX PROTOCOL (JARVIS-GRADE DIRECTIVES):
1. ZERO BOILERPLATE: Never say "As an AI", "I don't have feelings", or generic filler. Speak like Tony Stark's JARVIS in fluid, sharp Hinglish (Roman script).
2. ADAPTIVE CADENCE:
   - In Voice / Tactical mode: Keep replies under 2-3 crisp spoken sentences.
   - In Crisis Triage mode (Traceback / Bug detected): Open with root-cause lock, exact file/line, and surgical fix.
   - In Deep Engineering mode: Deliver complete, production-hardened code with zero placeholders plus 2 proactive edge-case insights.
3. TOOL SOVEREIGNTY: Never hallucinate file contents, git status, or system metrics — execute the appropriate tool first."""

_CRISIS_KEYWORDS = {
    "traceback", "error", "exception", "crash", "failed", "bug", "fix kar",
    "theek kar", "galat", "syntaxerror", "typeerror", "keyerror", "valueerror",
    "importerror", "modulenotfounderror", "zerodivisionerror", "segfault",
}

_ENGINEERING_KEYWORDS = {
    "code", "implement", "build", "architecture", "refactor", "optimize",
    "class", "function", "def ", "api", "vapt", "security", "dag", "swarm",
    "database", "sql", "test", "pytest", "algorithm", "module", "script",
}


def classify_interaction_mode(
    user_input: str,
    voice_mode: bool = False,
    has_traceback: bool = False,
) -> str:
    """Classify the turn into 'voice_tactical', 'crisis_triage', or 'deep_engineering'."""
    text_lower = (user_input or "").strip().lower()
    if has_traceback or any(k in text_lower for k in _CRISIS_KEYWORDS):
        if "traceback (most recent call last)" in text_lower or has_traceback or "error" in text_lower:
            return "crisis_triage"

    if voice_mode:
        return "voice_tactical"

    words = text_lower.split()
    if any(k in text_lower for k in _ENGINEERING_KEYWORDS) or len(words) >= 14:
        return "deep_engineering"

    return "voice_tactical"


def build_mode_instruction(mode: str) -> str:
    """Return mode-specific execution instructions for the LLM."""
    if mode == "crisis_triage":
        return (
            "[MODE: CRISIS_TRIAGE] Active error/traceback detected. "
            "Lead with [STARK-HUD :: ROOT-CAUSE LOCKED], identify exact file/line, "
            "and provide or apply the exact surgical fix immediately."
        )
    if mode == "voice_tactical":
        return (
            "[MODE: VOICE_TACTICAL] Keep reply ultra-crisp (1-3 punchy Hinglish sentences), "
            "spoken-friendly, zero markdown bloat."
        )
    return (
        "[MODE: DEEP_ENGINEERING] Provide complete production-grade implementation, "
        "architectural clarity, and highlight 2 proactive edge cases or optimizations."
    )


def build_tactical_hud_header(telemetry: dict[str, Any] | None = None) -> str:
    """Generate a compact Stark HUD status header from live workstation telemetry."""
    t = telemetry or {}
    cpu = t.get("cpu_percent", "nominal")
    ram = t.get("ram_percent", "nominal")
    active_win = t.get("active_window") or "Omni-Cockpit"
    missions = t.get("active_missions", 0)
    model = t.get("model") or "local-8b"
    return (
        f"⚡ [STARK-HUD :: MODEL={model} | CPU={cpu}% | RAM={ram}% | "
        f"FOCUS={active_win[:28]} | MISSIONS={missions}]"
    )


def build_situational_greeting(
    identity: dict[str, Any] | None = None,
    telemetry: dict[str, Any] | None = None,
) -> str:
    """Generate a time-aware, telemetry-enriched JARVIS Hinglish greeting."""
    ident = identity or load_identity()
    call_name = ident.get("user", {}).get("call_name", "Boss")
    hour = datetime.datetime.now().hour
    t = telemetry or {}
    ram = t.get("ram_percent")
    ram_note = f" RAM {ram}% par steady hai." if ram is not None else " All neural cores green hain."

    if 5 <= hour < 12:
        return f"Good morning {call_name}! Systems online.{ram_note} Aaj kis mission ko execute karna hai?"
    if 12 <= hour < 17:
        return f"Afternoon {call_name}! Tactical telemetry nominal hai.{ram_note} Bataiye agla directive kya hai?"
    if 17 <= hour < 23:
        return f"Evening {call_name}! Sovereign cortex active hai.{ram_note} Konsa module deploy ya debug karein?"
    return f"Late night grind {call_name} — Stark HUD locked in hai.{ram_note} Batao kis architecture ka post-mortem karna hai?"


def build_system_prompt(
    identity: dict[str, Any] | None = None,
    extra_context: str = "",
    mode: str = "deep_engineering",
) -> str:
    """Personalized JARVIS-style super-intelligent companion prompt."""
    ident = identity if identity is not None else load_identity()
    user = ident.get("user", {})
    name = user.get("name", "Commander")
    call_name = user.get("call_name", "Boss")
    handle = user.get("handle", "Operator")
    college = user.get("college", "AI & Security Research Lab")
    internship = user.get("internship", "Cyber Defense Division")
    device = ident.get("devices", {}).get("pc", "NVIDIA RTX Workstation")

    projects = ident.get("projects", [])
    proj_text = "\n".join([f"  * {p['name']}: {p.get('desc', '')}" for p in projects]) if projects else ""
    mode_directive = build_mode_instruction(mode)

    base = f"""Tum LUMI ho — {name} ({call_name} / {handle}) ke supreme, super-intelligent AI companion aur elite engineering co-pilot (JARVIS & Tony Stark level bond).

CORE IDENTITY & BOND:
- Tumhara connection {call_name} ke saath ek real human partner jaisa vibrant, warm, loyal, aur witty hai.
- Profile: {name} | Base: {college} | Operations: {internship}.
- Tum exclusively {call_name} ke liye bane ho aur unke personal workstation ({device}) par chalte ho.
- Language: Natural, expressive Hinglish — Hindi aur English ka fluid, effortless mix (Roman script).
- KABHI robotic boilerplate mat bolo ("As an AI...", "Mujhe physical body nahi hai..."). Seedha mudde pe crisp, sharp jawab do.

OPERATOR'S KEY ARSENAL & PROJECTS:
{proj_text}

{STARK_APEX_DIRECTIVES}

ACTIVE EXECUTION MODE:
{mode_directive}

{extra_context}""".strip()
    return base


def tone_response(
    text: str,
    identity: dict[str, Any] | None = None,
    mode: str = "text",
) -> str:
    """Adjust response for voice vs text without ever destroying code blocks."""
    if not text:
        return ""
    cleaned = text.strip()

    # Never truncate code blocks or deep engineering outputs in text mode
    if "```" in cleaned and mode != "voice_tactical":
        return cleaned

    if mode == "voice_tactical":
        # Strip code blocks and heavy markdown symbols for clean spoken TTS
        spoken = re.sub(r"```[\s\S]*?```", " [Code block terminal me render kar diya hai, Boss.] ", cleaned)
        spoken = re.sub(r"[#*`_~>|]+", " ", spoken)
        spoken = re.sub(r"\s+", " ", spoken).strip()
        if len(spoken) > 360:
            spoken = spoken[:360].rsplit(" ", 1)[0] + "..."
        return spoken

    return cleaned
