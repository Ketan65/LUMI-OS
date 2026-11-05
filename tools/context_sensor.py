"""Tool bindings for LUMI Active Context Sensor — JARVIS Situational Awareness."""

from __future__ import annotations

from pathlib import Path

from core.context_sensor import ActiveContextSensor, get_context_sensor
from tools.registry import Tool, ToolRegistry


def register_context_sensor_tools(
    registry: ToolRegistry,
    workspace_root: str | Path = ".",
) -> ActiveContextSensor:
    sensor = get_context_sensor(workspace_root=workspace_root)

    def sense_active_context(include_clipboard: bool = True) -> str:
        """Captures live Windows workstation context: foreground window title/process, Git workspace changes, and classified clipboard telemetry."""
        ctx = sensor.capture_workstation_context()
        win = ctx["active_window"]
        clip = ctx["clipboard"]
        git = ctx["git"]

        lines = [
            "### 🛰️ JARVIS Live Workstation Telemetry",
            f"- **Active Window:** `{win['title']}` (`{win['process']}`, PID `{win['pid']}`)",
            f"- **Git Workspace:** branch `{git['branch']}` — `{git['modified_count']}` modified entries",
        ]
        if git["modified_files"]:
            lines.append(f"  - Modified: `{', '.join(git['modified_files'][:6])}`")
        lines.append(f"- **Clipboard Type:** `{clip['kind']}` — {clip['summary']}")
        if include_clipboard and clip.get("content"):
            lines.append(f"\n**Clipboard Content:**\n```\n{clip['content'][:1000]}\n```")
        return "\n".join(lines)

    def inspect_clipboard_error() -> str:
        """Inspects the Windows clipboard specifically for Python tracebacks, compiler errors, or code snippets and extracts actionable file/line diagnostics."""
        clip_text = sensor.get_clipboard_text()
        meta = sensor.classify_clipboard(clip_text)
        if meta["kind"] == "empty":
            return "Clipboard is currently empty."

        badge = "🚨 **ERROR DETECTED**" if meta.get("is_error") else f"📋 **{meta['kind'].upper()}**"
        lines = [
            f"### {badge} in Clipboard",
            f"- **Classification:** `{meta['kind']}`",
            f"- **Summary:** {meta['summary']}",
        ]
        if meta.get("locations"):
            lines.append(f"- **Pinpointed Files/Lines:** `{', '.join(meta['locations'])}`")
        if meta.get("exception_line"):
            lines.append(f"- **Exception / Fault:** `{meta['exception_line']}`")
        lines.append(f"\n**Raw Clipboard Payload:**\n```\n{clip_text[:1400]}\n```")
        return "\n".join(lines)

    registry.register(
        Tool(
            name="sense_active_context",
            description=(
                "Captures real-time Windows 11 situational awareness without heavy screenshots: "
                "active foreground window title & process, Git dirty files, and clipboard telemetry."
            ),
            params_schema={
                "type": "object",
                "properties": {
                    "include_clipboard": {
                        "type": "boolean",
                        "description": "Whether to include the clipboard text excerpt (default true).",
                        "default": True,
                    },
                },
            },
            handler=sense_active_context,
            risk="auto",
        )
    )

    registry.register(
        Tool(
            name="inspect_clipboard_error",
            description=(
                "Inspects the user's clipboard for Python tracebacks, compiler/terminal errors, "
                "URLs, or code snippets and extracts file & line diagnostics."
            ),
            params_schema={
                "type": "object",
                "properties": {},
            },
            handler=inspect_clipboard_error,
            risk="auto",
        )
    )

    return sensor
