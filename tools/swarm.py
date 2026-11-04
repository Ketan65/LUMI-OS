"""Tool wrapper for LUMI Autonomous Software Engineering Swarm (Phase 9)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.swarm import SwarmCoordinator
from tools.registry import Tool, ToolRegistry


def register_swarm_tools(registry: ToolRegistry, orchestrator: Any, workspace_root: Path | str = "workspace") -> None:
    """Registers swarm_develop tool into ToolRegistry."""

    def swarm_develop(project_goal: str, project_name: str = "") -> str:
        """Autonomous Multi-Agent Software Engineering Team (Architect, Coder, Tester, Debugger)

        that designs, codes, tests, and self-heals complete projects in workspace/.
        """
        if not project_goal or not project_goal.strip():
            return "Please provide a valid project goal description."

        brain = getattr(orchestrator, "brain", None)
        if not brain:
            return "Error: Brain is not initialized on the orchestrator."

        coordinator = SwarmCoordinator(workspace_root=workspace_root, brain=brain)
        try:
            res = coordinator.develop(goal=project_goal.strip(), project_name=project_name.strip() or None)
            return res.get("summary", "Swarm development completed.")
        except Exception as exc:
            return f"Swarm development error: {exc}"

    registry.register(
        Tool(
            name="swarm_develop",
            description="Autonomous Multi-Agent Software Engineering Team (Architect, Coder, Tester, Debugger) that creates, codes, tests, and self-heals complete projects in workspace/.",
            params_schema={
                "type": "object",
                "properties": {
                    "project_goal": {
                        "type": "string",
                        "description": "High-level goal or specifications for the project to build.",
                    },
                    "project_name": {
                        "type": "string",
                        "description": "Optional snake_case folder name for the project.",
                    },
                },
                "required": ["project_goal"],
            },
            handler=swarm_develop,
            risk="ask",
        )
    )
