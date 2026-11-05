"""Sandbox tools — run_python for executing isolated scripts inside workspace/.

Security & Isolation:
  - Cwd locked to workspace/ (never LUMI root or sensitive directories).
  - Subprocess executed with -I (isolated mode: ignores PYTHONPATH and user site-packages).
  - Hard timeout (default 10s).
  - Policy risk: "ask" (never runs silently without explicit user approval).
  - Output capped at 4,000 characters to prevent context bloat.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from tools.registry import Tool, ToolRegistry
from safety.command_shield import CommandShield

DEFAULT_TIMEOUT_SEC = 10.0
MAX_OUTPUT_CHARS = 4000


def make_python_runner(workspace_path: str | Path) -> Callable[[str], str]:
    """Creates a run_python handler bound to a validated workspace path."""
    ws = Path(workspace_path).expanduser().resolve()
    ws.mkdir(parents=True, exist_ok=True)

    def run_python(code: str) -> str:
        """Executes python code snippet in an isolated subprocess."""
        if not code or not code.strip():
            return "No code provided to execute."

        # Intercept via CommandShield
        is_safe, reason = CommandShield.inspect_python_code(code)
        if not is_safe:
            return reason

        # Prepare execution in workspace
        try:
            # -I : isolated mode (no pythonpath, no user site packages)
            # -B : don't write .pyc files
            cmd = [sys.executable, "-I", "-B", "-c", code]
            proc = subprocess.run(
                cmd,
                cwd=str(ws),
                capture_output=True,
                text=True,
                timeout=DEFAULT_TIMEOUT_SEC,
                shell=False,
            )

            stdout = proc.stdout.strip()
            stderr = proc.stderr.strip()
            code_num = proc.returncode

            sections: list[str] = []
            if code_num == 0:
                sections.append(f"[Exit code: 0]")
            else:
                sections.append(f"[Exit code: {code_num} (Failed)]")

            if stdout:
                sections.append(f"Output:\n{stdout}")
            if stderr:
                sections.append(f"Stderr:\n{stderr}")
            if not stdout and not stderr:
                sections.append("(No output produced)")

            full_result = "\n\n".join(sections)
            if len(full_result) > MAX_OUTPUT_CHARS:
                full_result = full_result[:MAX_OUTPUT_CHARS] + f"\n...[truncated to {MAX_OUTPUT_CHARS} chars]"
            return full_result

        except subprocess.TimeoutExpired:
            return f"Error: Execution timed out after {DEFAULT_TIMEOUT_SEC} seconds."
        except Exception as exc:
            return f"Execution error: {exc}"

    return run_python


def make_command_runner(workspace_path: str | Path) -> Callable[[str, int], str]:
    """Creates a run_command handler for terminal execution (PowerShell / Shell)."""
    ws = Path(workspace_path).expanduser().resolve()
    ws.mkdir(parents=True, exist_ok=True)

    def run_command(command: str, timeout: int = 30) -> str:
        """Executes terminal commands (git, pytest, npm, pip, etc.) with timeout and captures output."""
        if not command or not command.strip():
            return "No command provided."

        # Intercept via CommandShield
        is_safe, reason = CommandShield.inspect_command(command)
        if not is_safe:
            return reason

        try:
            timeout_sec = min(max(1, int(timeout)), 120)
        except Exception:
            timeout_sec = 30

        try:
            import re
            # Since cwd is already workspace/, strip redundant 'workspace/' or 'workspace\' prefixes
            norm_cmd = re.sub(r'(^|[\s"\'])workspace[/\\]', r'\1', command.strip())
            proc = subprocess.run(
                norm_cmd,
                cwd=str(ws),
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                shell=True,
            )
            stdout = proc.stdout.strip()
            stderr = proc.stderr.strip()
            code_num = proc.returncode

            sections = [f"[Exit code: {code_num}]"]
            if stdout:
                sections.append(f"STDOUT:\n{stdout}")
            if stderr:
                sections.append(f"STDERR:\n{stderr}")
            if not stdout and not stderr:
                sections.append("(Command produced no output)")

            res = "\n\n".join(sections)
            if len(res) > MAX_OUTPUT_CHARS:
                res = res[:MAX_OUTPUT_CHARS] + f"\n...[truncated to {MAX_OUTPUT_CHARS} chars]"
            return res
        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {timeout_sec} seconds."
        except Exception as exc:
            return f"Command execution error: {exc}"

    return run_command


def register_sandbox_tools(registry: ToolRegistry, workspace_path: str | Path) -> None:
    runner = make_python_runner(workspace_path)
    cmd_runner = make_command_runner(workspace_path)
    registry.register(Tool(
        name="run_python",
        description="Executes a Python code snippet in an isolated subprocess within workspace/.",
        params_schema={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "The Python source code string to execute."},
            },
            "required": ["code"],
        },
        handler=runner,
        risk="ask",
    ))
    registry.register(Tool(
        name="run_command",
        description="Executes any terminal shell command (git, pytest, pip, npm, cargo, python, etc.) in the workspace directory and returns stdout/stderr.",
        params_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command line string to execute."},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 30, max 120).", "default": 30},
            },
            "required": ["command"],
        },
        handler=cmd_runner,
        risk="ask",
    ))
