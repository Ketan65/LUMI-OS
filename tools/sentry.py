"""Sentry tools for LUMI — Phase 7 AMBIE-SENTRY.

Provides the model and user with real-time proactive sentry telemetry.
"""

from __future__ import annotations

from typing import Any

from safety.sentry import AmbieSentry, sentry_status_text
from tools.registry import Tool, ToolRegistry


def register_sentry_tools(registry: ToolRegistry, sentry: AmbieSentry) -> None:
    def get_sentry_status() -> str:
        return sentry_status_text(sentry)

    registry.register(
        Tool(
            name="sentry_status",
            description=(
                "Returns the real-time proactive guardian status of LUMI Ambie-Sentry. "
                "Shows battery state, RAM usage, downloads watcher status, and recent proactive guardian events."
            ),
            params_schema={
                "type": "object",
                "properties": {},
            },
            handler=get_sentry_status,
            risk="auto",
        )
    )
