"""Context-Isolated Subagent Engine for LUMI-OS.

Runs multi-step codebase exploration, verification, or web scouting inside an
isolated temporary conversation buffer (`sub_messages`) so intermediate file
dumps and tool outputs never pollute `Orchestrator.session` ("Context Rot").
"""

from __future__ import annotations

from typing import Any

from core.resilient_parser import coerce_tool_arguments, repair_and_parse_json
from core.tool_watchdog import execute_tool_with_watchdog
from tools.registry import Tool, ToolRegistry

MAX_SUMMARY_CHARS = 1200
MAX_TOOL_OUTPUT_CHARS = 2000

ROLE_ALLOWLISTS: dict[str, set[str]] = {
    "research": {
        "list_files",
        "read_file",
        "search_files",
        "grep_search",
        "repo_structural_map",
        "repo_symbol_locate",
    },
    "verifier": {
        "read_file",
        "list_files",
        "run_python",
        "run_command",
        "grep_search",
    },
    "scout": {
        "web_search",
        "web_read",
        "browse_page",
        "read_file",
        "search_files",
    },
}

ROLE_PROMPTS: dict[str, str] = {
    "research": (
        "You are LUMI's isolated Research Subagent. Use read-only tools to inspect "
        "relevant files and symbols, then return ONLY a crisp, factual distilled "
        "summary under 1000 characters."
    ),
    "verifier": (
        "You are LUMI's isolated Verifier Subagent. Inspect files and execute checks/tests "
        "to validate correctness, then return ONLY a concise PASS/FAIL verification report "
        "under 1000 characters."
    ),
    "scout": (
        "You are LUMI's isolated Scout Subagent. Gather web or workspace facts quickly "
        "and return ONLY a concise distilled brief under 1000 characters."
    ),
}


def _truncate(text: str, limit: int) -> str:
    clean = (text or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 3)].rstrip() + "..."


class SubagentRunner:
    """Executes context-isolated multi-step subagents without mutating parent session."""

    def __init__(
        self,
        orchestrator: Any = None,
        brain: Any = None,
        registry: ToolRegistry | None = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.brain = brain
        self.registry = registry

    def _allowed_schemas(self, registry: ToolRegistry | None, role: str) -> tuple[list[dict] | None, set[str]]:
        allow = ROLE_ALLOWLISTS.get(role, ROLE_ALLOWLISTS["research"])
        if registry is None:
            return None, allow
        schemas = [
            s for s in registry.to_llm_schemas()
            if (s.get("function") or {}).get("name") in allow
        ]
        return (schemas or None), allow

    def run_subagent(
        self,
        role: str = "research",
        task: str = "",
        max_steps: int = 4,
    ) -> dict[str, Any]:
        """Runs a multi-step tool loop in a private message buffer and returns a compact summary."""
        role_norm = (role or "research").strip().lower()
        if role_norm not in ROLE_ALLOWLISTS:
            role_norm = "research"

        task_str = (task or "").strip()
        if not task_str:
            return {
                "role": role_norm,
                "task": "",
                "steps_taken": 0,
                "tools_used": [],
                "summary": "Error: Please provide a non-empty task.",
            }

        active_brain = self.brain or getattr(self.orchestrator, "brain", None)
        if active_brain is None:
            return {
                "role": role_norm,
                "task": task_str,
                "steps_taken": 0,
                "tools_used": [],
                "summary": "Error: No brain attached to SubagentRunner.",
            }

        active_registry = self.registry or getattr(self.orchestrator, "registry", None)
        allowed_schemas, allowed_names = self._allowed_schemas(active_registry, role_norm)

        sub_messages: list[dict[str, Any]] = [
            {"role": "system", "content": ROLE_PROMPTS[role_norm]},
            {"role": "user", "content": task_str},
        ]

        steps_taken = 0
        tools_used: list[str] = []
        collected_outputs: list[str] = []
        final_report = ""
        call_seq = 0
        budget = max(1, int(max_steps))

        for _ in range(budget):
            steps_taken += 1
            reply = active_brain.chat(sub_messages, tools=allowed_schemas)
            tool_calls = getattr(reply, "tool_calls", None) or []
            if not tool_calls:
                final_report = (getattr(reply, "text", "") or "").strip()
                break

            wire_calls: list[dict[str, Any]] = []
            resolved_calls: list[tuple[str, str, dict[str, Any]]] = []
            for tc in tool_calls:
                call_seq += 1
                cid = f"subcall_{call_seq}"
                name = str(tc.get("name") or "")
                raw_args = tc.get("args") or {}
                args = repair_and_parse_json(raw_args) if isinstance(raw_args, str) else (
                    dict(raw_args) if isinstance(raw_args, dict) else {"input": str(raw_args)}
                )
                wire_calls.append({
                    "id": cid,
                    "type": "function",
                    "function": {"name": name, "arguments": args},
                })
                resolved_calls.append((cid, name, args))

            sub_messages.append({
                "role": "assistant",
                "content": getattr(reply, "text", "") or "",
                "tool_calls": wire_calls,
            })

            for cid, name, args in resolved_calls:
                tool_res = self._execute_isolated_tool(active_registry, allowed_names, name, args)
                tools_used.append(name)
                collected_outputs.append(f"[{name}]: {_truncate(tool_res, 300)}")
                sub_messages.append({
                    "role": "tool",
                    "tool_call_id": cid,
                    "content": _truncate(tool_res, MAX_TOOL_OUTPUT_CHARS),
                })

        if not final_report:
            if collected_outputs:
                final_report = "Collected subagent findings:\n" + "\n".join(collected_outputs)
            else:
                final_report = "(subagent returned no findings)"

        return {
            "role": role_norm,
            "task": task_str,
            "steps_taken": steps_taken,
            "tools_used": tools_used,
            "summary": _truncate(final_report, MAX_SUMMARY_CHARS),
        }

    def _execute_isolated_tool(
        self,
        registry: ToolRegistry | None,
        allowed_names: set[str],
        name: str,
        args: dict[str, Any],
    ) -> str:
        if name not in allowed_names:
            return f"Error: Tool '{name}' is not permitted for this subagent role."
        tool = registry.get(name) if registry else None
        if tool is None:
            return f"Error: Unknown tool '{name}'."

        gate = getattr(self.orchestrator, "gate", None)
        if gate is not None:
            mem = getattr(self.orchestrator, "memory", None)
            sid = mem.session_id if mem else ""
            verdict, reason = gate.check(name, tool.risk, sid, args)
            if verdict == "block":
                return gate.block_message(reason) if hasattr(gate, "block_message") else f"Blocked: {reason}"

        coerced = coerce_tool_arguments(tool.params_schema, args)
        result, _ = execute_tool_with_watchdog(tool, coerced, timeout_sec=20.0)
        return result


def register_subagent_tools(
    registry: ToolRegistry,
    orchestrator: Any = None,
) -> SubagentRunner:
    """Registers `invoke_subagent` in the shared ToolRegistry."""
    runner = SubagentRunner(orchestrator=orchestrator, registry=registry)

    def invoke_subagent(role: str = "research", task: str = "") -> str:
        """Runs a context-isolated subagent ('research', 'verifier', or 'scout') and returns a distilled summary."""
        res = runner.run_subagent(role=role, task=task)
        used = ", ".join(res["tools_used"]) if res["tools_used"] else "none"
        return (
            f"### 🕵️ Subagent [{res['role'].upper()}] Report ({res['steps_taken']} steps)\n"
            f"- **Tools Used:** `{used}`\n\n"
            f"{res['summary']}"
        )

    registry.register(
        Tool(
            name="invoke_subagent",
            description=(
                "Spawns a context-isolated subagent ('research', 'verifier', or 'scout') to perform "
                "multi-step inspection or verification without polluting the main chat context."
            ),
            params_schema={
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "description": "Subagent specialization: 'research' (read-only code inspection), 'verifier' (tests/checks), or 'scout' (web/doc lookup).",
                        "enum": ["research", "verifier", "scout"],
                        "default": "research",
                    },
                    "task": {
                        "type": "string",
                        "description": "Clear, specific task or question for the subagent to investigate and summarize.",
                    },
                },
                "required": ["task"],
            },
            handler=invoke_subagent,
            risk="auto",
        )
    )
    return runner
