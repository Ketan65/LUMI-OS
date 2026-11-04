"""Tool bindings for LUMI Counterfactual Pre-Flight World Model (Phase 27)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.world_model import WorldModelSimulator
from tools.registry import Tool, ToolRegistry


def register_world_model_tools(
    registry: ToolRegistry,
    workspace_root: str | Path = "workspace",
    brain: Any = None,
) -> WorldModelSimulator:
    simulator = WorldModelSimulator(workspace_root=workspace_root, brain=brain)

    def simulate_and_apply_patch(
        file_path: str,
        candidate_code: str = "",
        optimization_goal: str = "",
        commit_if_passed: bool = True,
    ) -> str:
        """Simulates a code patch in an isolated shadow sandbox across 3 gates (AST, CWE Security, Runtime/Tests) and commits only if all pass."""
        res = simulator.simulate_and_commit(
            file_path=file_path,
            candidate_code=candidate_code or None,
            optimization_goal=optimization_goal or None,
            commit_if_passed=commit_if_passed,
        )
        if not res.get("success"):
            return f"❌ World-Model Simulation Error: {res.get('error')}"

        g1 = res["gates"]["gate1_ast"]
        g2 = res["gates"]["gate2_security"]
        g3 = res["gates"]["gate3_runtime"]
        lines = [
            f"### 🔮 Counterfactual Pre-Flight Simulation: `{Path(res['file']).name}`",
            f"**Verdict:** `{res['verdict']}` | **Committed to Disk:** `{res['committed']}` | **Time:** `{res['elapsed_ms']}ms`",
            "",
            "**Three-Gate Pre-Flight Verification:**",
            f"1. **Gate 1 (AST Syntax):** {'✅ PASS' if g1['passed'] else '❌ FAIL'} — {g1['message']}",
            f"2. **Gate 2 (Cyber-Sentinel CWE Gate):** {'✅ PASS' if g2['passed'] else '❌ FAIL'} — Score `{g2['security_score']}/100` ({g2['vulnerabilities_count']} CWEs)",
            f"3. **Gate 3 (Shadow Sandbox Runtime/Tests):** {'✅ PASS' if g3['passed'] else '❌ FAIL'} — `{g3.get('mode', 'n/a')}` ({g3.get('elapsed_ms', 0)}ms)",
        ]
        if res.get("diff"):
            lines.append(f"\n**Verified Diff:**\n```diff\n{res['diff'][:1200]}\n```")
        return "\n".join(lines)

    def profile_code_execution(code: str) -> str:
        """Profiles a Python code snippet's exact execution latency (ms) and peak heap memory (KB) in an isolated subprocess."""
        res = simulator.profile_code(code)
        status = "✅ OK" if res.get("ok") else f"❌ FAILED ({res.get('error')})"
        return (
            f"### ⏱️ World-Model Runtime & Memory Profile\n"
            f"- **Status:** {status}\n"
            f"- **Execution Latency:** `{res.get('elapsed_ms')} ms`\n"
            f"- **Peak Heap Memory (`tracemalloc`):** `{res.get('peak_kb')} KB`\n"
            f"- **Output:** `{res.get('stdout', '')[:400]}`"
        )

    registry.register(
        Tool(
            name="simulate_and_apply_patch",
            description="Simulates a code modification in an isolated shadow sandbox across 3 verification gates (AST, Security CWEs, Unit Tests) before committing.",
            params_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Target Python file path"},
                    "candidate_code": {"type": "string", "description": "Proposed replacement Python code (optional if optimization_goal is given)"},
                    "optimization_goal": {"type": "string", "description": "Natural language optimization or refactoring goal"},
                    "commit_if_passed": {"type": "boolean", "description": "Whether to atomically commit if all 3 gates pass (default true)"},
                },
                "required": ["file_path"],
            },
            handler=simulate_and_apply_patch,
            risk="auto",
        )
    )

    registry.register(
        Tool(
            name="profile_code_execution",
            description="Profiles Python code execution latency (ms) and peak heap memory usage (KB) via tracemalloc in an isolated subprocess.",
            params_schema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code snippet to profile"},
                },
                "required": ["code"],
            },
            handler=profile_code_execution,
            risk="auto",
        )
    )

    return simulator
