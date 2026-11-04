"""Agent Planner tool — BRAIN (Phase 3).

Exposes execute_goal as a first-class tool for autonomous multi-step execution.
"""

from __future__ import annotations

from typing import Any

from tools.registry import Tool, ToolRegistry


def make_goal_executor(orchestrator: Any):
    def run_goal(goal: str) -> str:
        from core.planner import execute_goal
        if not goal or not goal.strip():
            return "Error: goal text required (e.g. 'Create a script that fetches headlines and saves to workspace/news.txt')."
        return execute_goal(goal.strip(), orchestrator)
    return run_goal


def register_planner_tools(registry: ToolRegistry, orchestrator: Any) -> None:
    handler = make_goal_executor(orchestrator)
    registry.register(
        Tool(
            name="execute_goal",
            description=(
                "Decomposes a complex multi-step objective into sequential steps, executes tools autonomously, "
                "handles self-correction on errors, and returns a verified progress checklist. "
                "Use this for multi-file creation, testing, complex scripts, or multi-stage automation tasks."
            ),
            params_schema={
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "High-level goal description to plan and execute.",
                    },
                },
                "required": ["goal"],
            },
            handler=handler,
            risk="auto",
        )
    )
