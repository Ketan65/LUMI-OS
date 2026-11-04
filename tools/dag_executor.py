"""Tool bindings for LUMI Topological DAG Mission Executor (Phase 26)."""

from __future__ import annotations

from typing import Any

from core.dag_executor import AutonomousDAGExecutor
from tools.registry import Tool, ToolRegistry


def register_dag_executor_tools(
    registry: ToolRegistry,
    brain: Any = None,
) -> AutonomousDAGExecutor:
    executor = AutonomousDAGExecutor(registry=registry, brain=brain)

    def execute_dag_mission(mission: str) -> str:
        """Decomposes a complex goal into a parallel topological DAG, pipes outputs across nodes, and self-heals errors."""
        if not mission or not mission.strip():
            return "Please provide a valid mission description."
        res = executor.execute_mission(mission.strip())
        return res["summary"]

    def inspect_dag_history(limit: int = 5) -> str:
        """Returns execution telemetry for recent DAG missions."""
        recent = executor.history[-max(1, min(10, int(limit))):]
        if not recent:
            return "No DAG missions executed in this session yet."
        lines = [f"### 📊 Recent DAG Missions ({len(recent)})"]
        for item in reversed(recent):
            badge = "✅" if item["ok"] else "⚠️"
            lines.append(
                f"- {badge} **{item['mission']}** — `{item['nodes_succeeded']}/{item['nodes_total']}` nodes "
                f"({item['waves_count']} waves, {item['nodes_healed']} healed, {item['elapsed_ms']}ms)"
            )
        return "\n".join(lines)

    registry.register(
        Tool(
            name="execute_dag_mission",
            description="Decomposes a multi-step engineering mission into a parallel Directed Acyclic Graph (DAG), pipes outputs between nodes, and self-heals failures.",
            params_schema={
                "type": "object",
                "properties": {
                    "mission": {"type": "string", "description": "High-level multi-step engineering mission to execute"},
                },
                "required": ["mission"],
            },
            handler=execute_dag_mission,
            risk="auto",
        )
    )

    registry.register(
        Tool(
            name="inspect_dag_history",
            description="Returns telemetry and wave statistics for recent DAG missions.",
            params_schema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of recent missions to list (default 5)"},
                },
            },
            handler=inspect_dag_history,
            risk="auto",
        )
    )

    return executor
