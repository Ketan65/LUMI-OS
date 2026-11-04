"""Autonomous Goal Decomposer and Multi-Step Execution Engine — BRAIN (Phase 3).

Allows LUMI to accept high-level goals, plan sequential steps, execute tools,
diagnose errors, and perform autonomous self-healing.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

PLANNER_SYSTEM_PROMPT = """You are LUMI's Autonomous Goal Planning Cortex.
Given a user's high-level goal and available tools, break it down into 2 to 5 structured sequential steps.
Respond ONLY with a valid JSON array of objects.
Each object must have:
- "step": integer (1-based index)
- "title": concise action title in Hinglish/English
- "tool": name of tool to invoke (e.g. "write_file", "run_python", "web_search", "open_app", "read_file", "system_control", "analyze_screen")
- "args": dictionary of tool arguments
- "expected": expected result or validation criteria

Example Output:
[
  {"step": 1, "title": "Create Python script", "tool": "write_file", "args": {"path": "workspace/app.py", "content": "print('hello')"}, "expected": "File written"},
  {"step": 2, "title": "Run script to verify", "tool": "run_python", "args": {"code": "import app"}, "expected": "Exit code 0"}
]"""


def extract_json_array(text: str) -> list[dict] | None:
    """Extracts JSON array from text, stripping markdown code blocks if present."""
    clean = text.strip()
    match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", clean)
    if match:
        clean = match.group(1).strip()
    elif clean.find("[") != -1 and clean.rfind("]") != -1:
        clean = clean[clean.find("[") : clean.rfind("]") + 1]

    try:
        data = json.loads(clean)
        if isinstance(data, list) and len(data) > 0:
            return data
    except Exception:
        pass
    return None


def decompose_goal(goal: str, brain: Any, available_tools: list[str] | None = None) -> list[dict]:
    """Decompose high-level goal into actionable sequential steps."""
    tools_hint = ", ".join(available_tools) if available_tools else "write_file, read_file, run_python, web_search, open_app, analyze_screen, system_control"
    prompt = (
        f"Available Tools: {tools_hint}\n\n"
        f"Goal: {goal}\n\n"
        f"Decompose this into 2 to 5 steps as a JSON array. Remember to target files in 'workspace/'."
    )

    messages = [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    try:
        reply = brain.chat(messages, tools=None, temperature=0.1)
        content = reply.text if hasattr(reply, "text") else str(reply)
        steps = extract_json_array(content)
        if steps:
            return steps
    except Exception as exc:
        print(f"Goal decomposition warning: {exc}")

    # Heuristic fallback if LLM decomposition unavailable
    return [
        {
            "step": 1,
            "title": f"Execute goal task",
            "tool": "run_python" if "python" in goal.lower() or "script" in goal.lower() else "web_search",
            "args": {"code": f"# {goal}\nprint('Executing goal: {goal}')"} if "python" in goal.lower() else {"query": goal},
            "expected": "Task output produced",
        }
    ]


def execute_goal(goal: str, orchestrator: Any) -> str:
    """Execute goal autonomously with step-by-step progress tracking and self-correction."""
    reg = getattr(orchestrator, "registry", None)
    tool_names = [t.name for t in reg.list_all()] if reg else []
    steps = decompose_goal(goal, orchestrator.brain, tool_names)

    lines: list[str] = [
        f"### 🎯 Autonomous Goal Execution: {goal}",
        "",
        "**Execution Plan & Progress:**",
    ]

    success_count = 0
    total_steps = len(steps)

    for item in steps:
        s_num = item.get("step", 1)
        s_title = item.get("title", f"Step {s_num}")
        tool_name = item.get("tool", "")
        args = item.get("args") or {}
        if not isinstance(args, dict):
            args = {"input": str(args)}

        tool = reg.get(tool_name) if reg else None
        if not tool:
            lines.append(f"- ❌ Step {s_num}: `{s_title}` — Tool `{tool_name}` not found in registry.")
            continue

        # Execute step
        try:
            res = str(tool.handler(**args))
            is_err = "error" in res.lower() or "failed" in res.lower() or "exit code: 1" in res.lower()
        except Exception as exc:
            res = f"Execution error: {exc}"
            is_err = True

        # If failed, attempt self-healing / error recovery
        if is_err:
            fix_prompt = [
                {
                    "role": "system",
                    "content": "You are LUMI's Self-Correction engine. Given a tool error, produce corrected JSON arguments.",
                },
                {
                    "role": "user",
                    "content": f"Tool '{tool_name}' failed with error:\n{res}\nOriginal arguments:\n{json.dumps(args)}\nProvide corrected JSON arguments object ONLY.",
                },
            ]
            try:
                fix_reply = orchestrator.brain.chat(fix_prompt, temperature=0.1)
                fix_content = fix_reply.text if hasattr(fix_reply, "text") else str(fix_reply)
                match = re.search(r"\{[\s\S]*?\}", fix_content)
                if match:
                    new_args = json.loads(match.group(0))
                    retry_res = str(tool.handler(**new_args))
                    retry_err = "error" in retry_res.lower() or "failed" in retry_res.lower()
                    if not retry_err:
                        lines.append(f"- [x] Step {s_num}: `{s_title}` — ⚠️ Recovered: {retry_res[:100]}")
                        success_count += 1
                        continue
            except Exception:
                pass

            lines.append(f"- ⚠️ Step {s_num}: `{s_title}` — Failed: {res[:120]}")
        else:
            summary = res.strip()[:100].replace("\n", " ")
            lines.append(f"- [x] Step {s_num}: `{s_title}` — ✅ Succeeded: {summary}")
            success_count += 1

    lines.append("")
    if success_count == total_steps:
        lines.append(f"✨ **Goal Completed Successfully** ({success_count}/{total_steps} steps succeeded autonomously).")
    else:
        lines.append(f"⚠️ **Goal Partially Completed** ({success_count}/{total_steps} steps succeeded).")

    return "\n".join(lines)
