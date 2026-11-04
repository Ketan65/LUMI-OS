"""DAG-EXECUTOR: Topological Parallel Wave & Self-Healing Mission Engine (Phase 26).

Upgrades LUMI from 1D sequential planning to a full Directed Acyclic Graph (DAG) Execution Cortex:
1. Topological Wave Scheduling (Kahn's algorithm) — runs independent nodes in parallel waves.
2. Dynamic Output Piping (`$node_id.output`) — passes real runtime outputs to downstream nodes.
3. Closed-Loop Verification & Reflexion Self-Healing — validates node outputs and auto-repairs failed tool calls.
4. Mission Telemetry & Execution Trace Persistence.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger("lumi.dag_executor")

DAG_PLANNER_PROMPT = """You are LUMI's Autonomous Topological DAG Mission Planner.
Decompose the user's complex mission into a Directed Acyclic Graph (DAG) of 2 to 6 executable nodes.
Respond ONLY with a valid JSON array of node objects:
[
  {
    "id": "node_1",
    "title": "Write core module",
    "tool": "write_file",
    "args": {"path": "workspace/service.py", "content": "..."},
    "depends_on": [],
    "expected_contains": "written"
  },
  {
    "id": "node_2",
    "title": "Audit security of module",
    "tool": "vapt_deep_scan",
    "args": {"file_path": "workspace/service.py"},
    "depends_on": ["node_1"],
    "expected_contains": "FORTIFIED"
  }
]
You may reference a parent node's output in downstream args using `$node_1.output`."""


@dataclass
class DAGNode:
    id: str
    title: str
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    expected_contains: str = ""
    status: str = "PENDING"
    output: str = ""
    retries: int = 0
    elapsed_ms: float = 0.0
    wave: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AutonomousDAGExecutor:
    """Executes multi-step missions as parallel topological waves with dynamic context piping and self-healing."""

    def __init__(self, registry: Any = None, brain: Any = None, max_workers: int = 4):
        self.registry = registry
        self.brain = brain
        self.max_workers = max_workers
        self.history: list[dict[str, Any]] = []

    def plan_dag(self, mission: str) -> list[DAGNode]:
        """Decomposes a high-level mission into a topological DAG of tool invocations."""
        tool_names = [t.name for t in self.registry.list_all()] if self.registry else []
        if self.brain is not None:
            try:
                prompt = (
                    f"Available Tools: {', '.join(tool_names[:35])}\n\n"
                    f"Mission: {mission}\n\n"
                    "Return ONLY a JSON array of DAG nodes (`id`, `title`, `tool`, `args`, `depends_on`, `expected_contains`)."
                )
                reply = self.brain.chat(
                    [
                        {"role": "system", "content": DAG_PLANNER_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                )
                raw = reply.text if hasattr(reply, "text") else str(reply)
                m = re.search(r"\[[\s\S]*\]", raw)
                if m:
                    parsed = json.loads(m.group(0))
                    if isinstance(parsed, list) and len(parsed) > 0:
                        nodes = []
                        for idx, item in enumerate(parsed):
                            if isinstance(item, dict):
                                nodes.append(
                                    DAGNode(
                                        id=str(item.get("id") or f"node_{idx + 1}"),
                                        title=str(item.get("title") or f"Task {idx + 1}"),
                                        tool=str(item.get("tool") or "run_python"),
                                        args=dict(item.get("args") or {}),
                                        depends_on=[str(d) for d in (item.get("depends_on") or [])],
                                        expected_contains=str(item.get("expected_contains") or ""),
                                    )
                                )
                        if nodes:
                            return nodes
            except Exception as exc:
                logger.debug("DAG LLM decomposition fallback: %s", exc)

        # Deterministic multi-node fallback DAG
        return [
            DAGNode(
                id="node_1",
                title="Execute primary analysis script",
                tool="run_python",
                args={"code": f"print('Mission initialized:', {mission!r})"},
                depends_on=[],
                expected_contains="Mission initialized",
            ),
        ]

    @staticmethod
    def compute_waves(nodes: list[DAGNode]) -> list[list[DAGNode]]:
        """Groups DAG nodes into parallel topological execution waves using Kahn's algorithm."""
        node_map: dict[str, DAGNode] = {n.id: n for n in nodes}
        in_degree: dict[str, int] = {n.id: 0 for n in nodes}
        dependents: dict[str, list[str]] = {n.id: [] for n in nodes}

        for n in nodes:
            valid_deps = [d for d in n.depends_on if d in node_map and d != n.id]
            n.depends_on = valid_deps
            in_degree[n.id] = len(valid_deps)
            for d in valid_deps:
                dependents[d].append(n.id)

        waves: list[list[DAGNode]] = []
        ready = [nid for nid, deg in in_degree.items() if deg == 0]
        visited: set[str] = set()
        wave_idx = 1

        while ready:
            current_wave: list[DAGNode] = []
            next_ready: list[str] = []
            for nid in ready:
                if nid in visited:
                    continue
                visited.add(nid)
                node = node_map[nid]
                node.wave = wave_idx
                current_wave.append(node)
                for child_id in dependents.get(nid, []):
                    in_degree[child_id] -= 1
                    if in_degree[child_id] == 0:
                        next_ready.append(child_id)
            if current_wave:
                waves.append(current_wave)
                wave_idx += 1
            ready = next_ready

        # If cycle existed, append remaining unvisited nodes in a final recovery wave
        remaining = [n for n in nodes if n.id not in visited]
        if remaining:
            for n in remaining:
                n.wave = wave_idx
            waves.append(remaining)

        return waves

    @staticmethod
    def _interpolate_args(args: dict[str, Any], outputs: dict[str, str]) -> dict[str, Any]:
        """Substitutes `$node_id.output` placeholders with actual runtime outputs from parent nodes."""
        resolved: dict[str, Any] = {}
        for k, v in args.items():
            if isinstance(v, str):
                new_val = v
                for nid, out_text in outputs.items():
                    placeholder = f"${nid}.output"
                    if placeholder in new_val:
                        new_val = new_val.replace(placeholder, out_text.strip())
                resolved[k] = new_val
            elif isinstance(v, dict):
                resolved[k] = AutonomousDAGExecutor._interpolate_args(v, outputs)
            else:
                resolved[k] = v
        return resolved

    @staticmethod
    def _is_failure_output(output: str, expected_contains: str = "") -> bool:
        low = output.lower()
        if any(err in low for err in ("traceback (most recent call last):", "[exit code: 1]", "[exit code: 2]", "execution error:", "syntaxerror:")):
            return True
        if low.startswith(("error:", "❌")):
            return True
        if expected_contains and expected_contains.lower() not in low:
            return True
        return False

    def _heal_node_args(self, node: DAGNode, resolved_args: dict[str, Any], error_output: str) -> dict[str, Any] | None:
        """Uses Reflexion Critic (LLM + deterministic rules) to repair failing tool arguments."""
        # Fast deterministic healing for run_python / run_command / write_file errors
        if node.tool == "run_python" and "code" in resolved_args and self.brain is not None:
            try:
                prompt = (
                    f"Tool `run_python` failed on node `{node.title}`.\n"
                    f"Original Code:\n```python\n{resolved_args['code']}\n```\n"
                    f"Error Output:\n```\n{error_output[:1000]}\n```\n"
                    f"Expected output substring: `{node.expected_contains}`\n\n"
                    "Return ONLY the corrected Python code inside ```python and ```."
                )
                rep = self.brain.chat(
                    [
                        {"role": "system", "content": "You are LUMI's DAG Reflexion Healer. Fix the failing Python code."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                )
                txt = rep.text if hasattr(rep, "text") else str(rep)
                m = re.search(r"```(?:python|py)?\s*([\s\S]*?)\s*```", txt)
                fixed_code = m.group(1).strip() if m else txt.strip()
                if fixed_code and fixed_code != resolved_args["code"]:
                    return {**resolved_args, "code": fixed_code}
            except Exception:
                pass

        if self.brain is not None:
            try:
                prompt = (
                    f"DAG Node `{node.id}` (`{node.title}`) calling tool `{node.tool}` failed.\n"
                    f"Arguments: {json.dumps(resolved_args)}\n"
                    f"Error Output: {error_output[:800]}\n"
                    f"Required output check: {node.expected_contains}\n"
                    "Return ONLY a corrected JSON arguments object."
                )
                rep = self.brain.chat(
                    [
                        {"role": "system", "content": "You are LUMI's DAG Reflexion Healer. Output valid JSON arguments object only."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                )
                txt = rep.text if hasattr(rep, "text") else str(rep)
                m = re.search(r"\{[\s\S]*\}", txt)
                if m:
                    new_args = json.loads(m.group(0))
                    if isinstance(new_args, dict):
                        return new_args
            except Exception as exc:
                logger.debug("DAG node healing fallback: %s", exc)
        return None

    def _execute_single_node(
        self,
        node: DAGNode,
        completed_outputs: dict[str, str],
        max_retries: int = 2,
    ) -> DAGNode:
        t0 = time.perf_counter()
        node.status = "RUNNING"

        if self.registry is None:
            node.status = "FAILED"
            node.output = "Error: No ToolRegistry attached to DAG Executor."
            node.elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
            return node

        tool_obj = self.registry.get(node.tool)
        if tool_obj is None:
            node.status = "FAILED"
            node.output = f"Error: Tool '{node.tool}' not found in registry."
            node.elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
            return node

        current_args = self._interpolate_args(node.args, completed_outputs)

        for attempt in range(max_retries + 1):
            try:
                res = str(tool_obj.handler(**current_args))
            except Exception as exc:
                res = f"Execution error: {exc}"

            failed = self._is_failure_output(res, node.expected_contains)
            if not failed:
                node.output = res
                node.status = "HEALED" if attempt > 0 else "COMPLETED"
                node.retries = attempt
                node.elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
                return node

            # Attempt self-healing if retries remain
            if attempt < max_retries:
                healed_args = self._heal_node_args(node, current_args, res)
                if healed_args is not None:
                    current_args = healed_args
                    node.args = healed_args
                    continue
                break

        node.output = res
        node.status = "FAILED"
        node.retries = max_retries
        node.elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        return node

    def execute_mission(
        self,
        mission: str,
        nodes: list[dict[str, Any] | DAGNode] | None = None,
        max_retries: int = 2,
    ) -> dict[str, Any]:
        """Executes a full DAG mission across parallel topological waves with context piping and self-healing."""
        t0 = time.perf_counter()
        if nodes is not None:
            dag_nodes = [
                n if isinstance(n, DAGNode) else DAGNode(
                    id=str(n.get("id") or f"node_{i+1}"),
                    title=str(n.get("title") or f"Step {i+1}"),
                    tool=str(n.get("tool") or "run_python"),
                    args=dict(n.get("args") or {}),
                    depends_on=list(n.get("depends_on") or []),
                    expected_contains=str(n.get("expected_contains") or ""),
                )
                for i, n in enumerate(nodes)
            ]
        else:
            dag_nodes = self.plan_dag(mission)

        waves = self.compute_waves(dag_nodes)
        completed_outputs: dict[str, str] = {}

        for wave_nodes in waves:
            if len(wave_nodes) == 1:
                done_node = self._execute_single_node(wave_nodes[0], completed_outputs, max_retries=max_retries)
                completed_outputs[done_node.id] = done_node.output
            else:
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(self.max_workers, len(wave_nodes))) as pool:
                    futures = {
                        pool.submit(self._execute_single_node, n, dict(completed_outputs), max_retries): n
                        for n in wave_nodes
                    }
                    for fut in concurrent.futures.as_completed(futures):
                        done_node = fut.result()
                        completed_outputs[done_node.id] = done_node.output

        total_elapsed = round((time.perf_counter() - t0) * 1000, 2)
        succeeded = sum(1 for n in dag_nodes if n.status in {"COMPLETED", "HEALED"})
        healed_count = sum(1 for n in dag_nodes if n.status == "HEALED")
        all_passed = succeeded == len(dag_nodes)

        report_lines = [
            f"### ⚡ LUMI Topological DAG Mission: {mission}",
            f"**Status:** `{'SUCCESS' if all_passed else 'PARTIAL'}` ({succeeded}/{len(dag_nodes)} nodes passed, {healed_count} self-healed) | **Waves:** `{len(waves)}` | **Time:** `{total_elapsed}ms`",
            "",
        ]
        for w_idx, wave in enumerate(waves, start=1):
            report_lines.append(f"**Wave {w_idx} ({len(wave)} parallel node{'s' if len(wave) > 1 else ''}):**")
            for n in wave:
                icon = "✅" if n.status == "COMPLETED" else ("🔧" if n.status == "HEALED" else "❌")
                deps = f" *(deps: {', '.join(n.depends_on)})*" if n.depends_on else ""
                preview = n.output.strip().replace("\n", " ")[:140]
                report_lines.append(
                    f"- {icon} **`{n.id}` ({n.title})** via `{n.tool}` [{n.status} in {n.elapsed_ms}ms]{deps}\n"
                    f"  - *Output:* `{preview}`"
                )

        payload = {
            "ok": all_passed,
            "mission": mission,
            "waves_count": len(waves),
            "nodes_total": len(dag_nodes),
            "nodes_succeeded": succeeded,
            "nodes_healed": healed_count,
            "nodes": [n.to_dict() for n in dag_nodes],
            "elapsed_ms": total_elapsed,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "summary": "\n".join(report_lines),
        }
        self.history.append(payload)
        return payload
