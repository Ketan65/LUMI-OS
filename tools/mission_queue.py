"""Tool bindings for LUMI Async Mission Queue — Non-Blocking Background Autonomy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.mission_queue import AsyncMissionQueue, get_mission_queue
from tools.registry import Tool, ToolRegistry


def register_mission_queue_tools(
    registry: ToolRegistry,
    orchestrator: Any = None,
    workspace_root: str | Path = "workspace",
    brain: Any = None,
) -> AsyncMissionQueue:
    queue = get_mission_queue(max_workers=2)
    resolved_brain = brain or getattr(orchestrator, "brain", None)

    def dispatch_background_mission(
        mission_goal: str,
        mission_kind: str = "dag",
        target_path: str = "",
    ) -> str:
        """Dispatches a heavy mission (`dag`, `swarm`, `research`, or `vapt`) to run asynchronously in the background worker pool without blocking chat."""
        goal = (mission_goal or "").strip()
        if not goal:
            return "Error: Please provide a non-empty `mission_goal`."
        kind = (mission_kind or "dag").strip().lower()

        def _execute_payload() -> Any:
            active_brain = resolved_brain or getattr(orchestrator, "brain", None)
            if kind == "swarm":
                from core.swarm import SwarmCoordinator
                coord = SwarmCoordinator(workspace_root=workspace_root, brain=active_brain)
                return coord.develop(goal=goal)
            if kind == "research":
                from core.researcher import DeepResearcher
                researcher = getattr(orchestrator, "researcher", None) or DeepResearcher(
                    workspace_root=workspace_root, brain=active_brain
                )
                return researcher.conduct_research(goal)
            if kind == "vapt":
                from core.cyber_sentinel import CyberSentinel
                sentinel = getattr(orchestrator, "cyber_sentinel", None) or CyberSentinel(
                    workspace_root=".", brain=active_brain
                )
                if target_path and Path(target_path).exists():
                    return sentinel.deep_scan_file(target_path)
                return sentinel.audit_attack_surface()
            # Default: topological DAG mission
            from core.dag_executor import AutonomousDAGExecutor
            dag = getattr(orchestrator, "dag_executor", None) or AutonomousDAGExecutor(
                registry=registry, brain=active_brain
            )
            return dag.execute_mission(goal)

        record = queue.submit_mission(
            name=goal[:100],
            kind=kind,
            fn=_execute_payload,
        )
        return (
            f"### 🚀 Background Mission Dispatched\n"
            f"- **Mission ID:** `{record['mission_id']}`\n"
            f"- **Kind:** `{record['kind']}`\n"
            f"- **Goal:** {record['name']}\n"
            f"- **Status:** `{record['status']}` (running in background `ThreadPoolExecutor`)\n"
            f"- *Tip:* Use `check_mission_queue(mission_id=\"{record['mission_id']}\")` or `/missions` anytime to inspect live progress and results."
        )

    def check_mission_queue(mission_id: str = "", status_filter: str = "") -> str:
        """Checks the live progress, event logs, and results of a specific background mission or lists all queued/running/completed missions."""
        mid = (mission_id or "").strip()
        if mid:
            m = queue.get_mission(mid)
            if not m:
                return f"Mission `{mid}` not found in queue."
            badge = {"queued": "⏳", "running": "⚙️", "completed": "✅", "failed": "❌"}.get(
                m["status"], "·"
            )
            lines = [
                f"### {badge} Mission Telemetry: `{m['mission_id']}`",
                f"- **Name:** {m['name']}",
                f"- **Kind:** `{m['kind']}` | **Status:** `{m['status'].upper()}` | **Progress:** `{m['progress']}%`",
                f"- **Started:** `{m['started_at'] or 'pending'}` | **Finished:** `{m['finished_at'] or 'in-progress'}` (`{m['elapsed_ms']}ms`)",
                "",
                "**Event Log:**",
            ]
            for ev in m.get("events", [])[-8:]:
                lines.append(f"- `{ev}`")
            if m.get("error"):
                lines.append(f"\n**Error:** `{m['error']}`")
            if m.get("result"):
                lines.append(f"\n**Result Summary:**\n{m['result'][:1200]}")
            return "\n".join(lines)

        missions = queue.list_missions(status=status_filter or None, limit=15)
        if not missions:
            return "No background missions in queue yet."
        lines = [f"### 📋 Async Mission Queue ({len(missions)} missions)"]
        for m in missions:
            badge = {"queued": "⏳", "running": "⚙️", "completed": "✅", "failed": "❌"}.get(
                m["status"], "·"
            )
            lines.append(
                f"- {badge} **`{m['mission_id']}`** [{m['kind']}] **{m['name'][:65]}** — "
                f"`{m['status']}` (`{m['progress']}%`, `{m['elapsed_ms']}ms`)"
            )
        return "\n".join(lines)

    registry.register(
        Tool(
            name="dispatch_background_mission",
            description=(
                "Submits a heavy engineering task ('dag', 'swarm', 'research', or 'vapt') "
                "to run asynchronously in a background worker thread without blocking interactive chat."
            ),
            params_schema={
                "type": "object",
                "properties": {
                    "mission_goal": {
                        "type": "string",
                        "description": "High-level goal, research topic, or engineering specification.",
                    },
                    "mission_kind": {
                        "type": "string",
                        "description": "Type of background mission: 'dag', 'swarm', 'research', or 'vapt'. Default 'dag'.",
                        "enum": ["dag", "swarm", "research", "vapt"],
                        "default": "dag",
                    },
                    "target_path": {
                        "type": "string",
                        "description": "Optional target file path (used when mission_kind='vapt').",
                        "default": "",
                    },
                },
                "required": ["mission_goal"],
            },
            handler=dispatch_background_mission,
            risk="auto",
        )
    )

    registry.register(
        Tool(
            name="check_mission_queue",
            description=(
                "Checks the status, progress percentage, event log, and output of a background mission "
                "by mission_id, or lists all recent background missions."
            ),
            params_schema={
                "type": "object",
                "properties": {
                    "mission_id": {
                        "type": "string",
                        "description": "Optional specific mission_id (e.g. 'msn_a1b2c3d4') to inspect in detail.",
                        "default": "",
                    },
                    "status_filter": {
                        "type": "string",
                        "description": "Optional status filter ('queued', 'running', 'completed', 'failed').",
                        "default": "",
                    },
                },
            },
            handler=check_mission_queue,
            risk="auto",
        )
    )

    return queue
