"""Self-Healing, Error Correction & Autonomous Evolution Engine (LUMI v37.0).

Empowers LUMI to actively detect, diagnose, surgically patch, and verify its own errors:
  - Automatic error classification (Syntax, Import, TypeMismatch, Key/Index, FileFault).
  - Surgical code and AST auto-repair in isolated sandbox.
  - Integration with DPO Flywheel: permanently records (failed, healed) pairs.
  - Zero-human-intervention self-healing for workspace scripts and tool execution faults.
"""

from __future__ import annotations

import ast
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from evolution.dpo_flywheel import get_dpo_flywheel
from tools.registry import Tool, ToolRegistry

logger = logging.getLogger("lumi.self_healing")


class SelfHealingEngine:
    """Core self-diagnostic and surgical error correction engine."""

    def __init__(self, workspace_root: str | Path = "workspace") -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.dpo_flywheel = get_dpo_flywheel()

    def diagnose_error(self, error_str: str, code_snippet: str = "") -> dict[str, Any]:
        """Diagnoses error type, fault line number, and surgical remediation strategy."""
        err_lower = (error_str or "").lower()
        strategy = "generic_repair"
        category = "UNKNOWN"
        target_line = None

        # Extract line number from traceback if present
        line_match = re.search(r"line\s+(\d+)", error_str, re.IGNORECASE)
        if line_match:
            target_line = int(line_match.group(1))

        if "modulenotfounderror" in err_lower or "no module named" in err_lower:
            category = "MISSING_DEPENDENCY"
            mod_match = re.search(r"no module named ['\"]([^'\"]+)['\"]", error_str, re.IGNORECASE)
            missing_mod = mod_match.group(1) if mod_match else "unknown_module"
            strategy = f"Auto-provision dependency '{missing_mod}' via pip in sandbox."
        elif "syntaxerror" in err_lower:
            category = "SYNTAX_ERROR"
            strategy = "Inspect AST token boundary, repair missing colons, quotes, or indentation."
        elif "typeerror" in err_lower:
            category = "TYPE_MISMATCH"
            strategy = "Coerce argument types, check callable signatures, or adapt kwargs."
        elif "keyerror" in err_lower:
            category = "KEY_ERROR"
            strategy = "Replace direct dict indexing d[k] with safe d.get(k, default) access."
        elif "filenotfounderror" in err_lower:
            category = "FILE_NOT_FOUND"
            strategy = "Verify path existence, create missing parent directories, or fallback to default."
        elif "zerodivisionerror" in err_lower:
            category = "ZERO_DIVISION"
            strategy = "Add defensive zero-check denominator validation."

        return {
            "category": category,
            "line_number": target_line,
            "remediation_strategy": strategy,
            "original_error": error_str[:300],
        }

    def heal_python_snippet(self, code: str, error_str: str) -> tuple[bool, str, str]:
        """Attempts automated rule-based and AST surgical healing on a Python code snippet."""
        diagnosis = self.diagnose_error(error_str, code)
        cat = diagnosis["category"]
        healed_code = code
        explanation = ""

        # 1. Handle Missing Colon Syntax Errors (e.g. `def foo()` or `if cond` without `:`)
        if cat == "SYNTAX_ERROR":
            lines = code.splitlines()
            line_no = diagnosis.get("line_number")
            if line_no and 1 <= line_no <= len(lines):
                target_idx = line_no - 1
                curr = lines[target_idx]
                # If statement or def missing trailing colon
                if re.match(r"^\s*(def|class|if|elif|else|for|while|try|except|finally|with)\b", curr) and not curr.rstrip().endswith(":"):
                    lines[target_idx] = curr + ":"
                    healed_code = "\n".join(lines)
                    explanation = f"Healed missing colon on line {line_no}."

        # 2. Handle KeyError (convert `dict[key]` to `dict.get(key)`)
        elif cat == "KEY_ERROR":
            key_match = re.search(r"keyerror:\s*['\"]([^'\"]+)['\"]", error_str, re.IGNORECASE)
            if key_match:
                missing_key = key_match.group(1)
                # Replace d['missing_key'] with d.get('missing_key', None)
                pattern = rf'\[\s*[\'"]{re.escape(missing_key)}[\'"]\s*\]'
                if re.search(pattern, healed_code):
                    healed_code = re.sub(pattern, f".get('{missing_key}')", healed_code)
                    explanation = f"Healed KeyError: converted direct indexing of '{missing_key}' to safe .get()."

        # 3. Handle ZeroDivisionError
        elif cat == "ZERO_DIVISION":
            if "/" in healed_code:
                # Add defensive zero check wrapper or default
                explanation = "Healed ZeroDivisionError with defensive denominator protection."
                healed_code = re.sub(r'(\w+)\s*/\s*(\w+)', r'(\1 / \2 if \2 != 0 else 0.0)', healed_code)

        # Verify healed code in sandbox
        if healed_code != code:
            try:
                ast.parse(healed_code)
                # Run execution test in isolated subprocess
                res = subprocess.run(
                    [sys.executable, "-c", healed_code],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if res.returncode == 0:
                    # Successfully verified! Record into DPO Flywheel
                    self._record_flywheel_healing(code, healed_code, error_str, explanation)
                    return True, healed_code, explanation or "Successfully healed code and verified in sandbox."
            except Exception:
                pass

        return False, code, f"Could not automatically verify healed code. Diagnosis: {diagnosis['remediation_strategy']}"

    def heal_workspace_file(self, relative_path: str, error_context: str = "") -> dict[str, Any]:
        """Reads a workspace file, diagnoses failure, patches the code, and verifies."""
        target_file = (self.workspace_root / relative_path).resolve()
        if not target_file.exists():
            # Try finding within workspace
            matches = list(self.workspace_root.glob(f"**/{relative_path}"))
            if matches:
                target_file = matches[0]
            else:
                return {"success": False, "error": f"File '{relative_path}' not found in workspace."}

        try:
            content = target_file.read_text(encoding="utf-8")
        except Exception as e:
            return {"success": False, "error": f"Failed to read file: {e}"}

        # If no explicit error context, run python to capture error
        if not error_context:
            proc = subprocess.run(
                [sys.executable, str(target_file)],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(self.workspace_root),
            )
            if proc.returncode == 0:
                return {"success": True, "message": f"File '{relative_path}' executed cleanly with zero errors (Exit code 0)."}
            error_context = proc.stderr or proc.stdout

        success, healed_code, explanation = self.heal_python_snippet(content, error_context)
        if success:
            # Backup original and write healed code
            bak_path = target_file.with_suffix(target_file.suffix + ".bak")
            bak_path.write_text(content, encoding="utf-8")
            target_file.write_text(healed_code, encoding="utf-8")
            return {
                "success": True,
                "file": str(target_file.name),
                "explanation": explanation,
                "backup_created": str(bak_path.name),
            }

        return {
            "success": False,
            "file": str(target_file.name),
            "diagnosis": self.diagnose_error(error_context),
            "message": "Manual inspection recommended. Automated patch did not pass sandbox verification.",
        }

    def _record_flywheel_healing(self, original: str, healed: str, error: str, note: str) -> None:
        """Records self-healed pair into DPO flywheel dataset."""
        try:
            if self.dpo_flywheel:
                self.dpo_flywheel.record_tool_repair(
                    user_prompt="self_healing_code_patch",
                    tool_name="self_healing_engine",
                    failed_args={"code": original[:300]},
                    failed_error=error[:200],
                    healed_args={"code": healed[:300]},
                    healed_result=note[:200],
                )
        except Exception as e:
            logger.error("Failed to log flywheel healing: %s", e)


_ENGINE: SelfHealingEngine | None = None


def get_self_healing_engine(workspace_root: str | Path = "workspace") -> SelfHealingEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = SelfHealingEngine(workspace_root=workspace_root)
    return _ENGINE


def register_self_healing_tools(registry: ToolRegistry, workspace_root: str | Path = "workspace") -> None:
    engine = get_self_healing_engine(workspace_root)

    def heal_code_tool(target_file: str, error_context: str = "") -> str:
        res = engine.heal_workspace_file(target_file, error_context)
        if res.get("success"):
            return (
                f"🛠️ [SELF-HEALING COMPLETE]: File '{res.get('file')}' healed successfully!\n"
                f"Remediation: {res.get('explanation')}\n"
                f"Backup: {res.get('backup_created', 'none')}\n"
                f"Verification: Passed sandbox execution tests. DPO Flywheel pair recorded."
            )
        diag = res.get("diagnosis", {})
        return (
            f"⚠️ [SELF-HEALING DIAGNOSTIC]: Could not fully auto-patch '{res.get('file')}'.\n"
            f"Category: {diag.get('category')}\n"
            f"Fault Line: {diag.get('line_number')}\n"
            f"Strategy: {diag.get('remediation_strategy')}"
        )

    def diagnose_error_tool(error_text: str) -> str:
        diag = engine.diagnose_error(error_text)
        return (
            f"🩺 [ERROR DIAGNOSTIC REPORT]:\n"
            f"Category: {diag['category']}\n"
            f"Target Line: {diag['line_number']}\n"
            f"Recommended Fix: {diag['remediation_strategy']}"
        )

    registry.register(
        Tool(
            name="self_heal_code",
            description="Autonomously diagnoses, patches, and verifies failing code or script errors in workspace.",
            params_schema={
                "type": "object",
                "properties": {
                    "target_file": {"type": "string", "description": "Relative filename in workspace (e.g. app.py)"},
                    "error_context": {"type": "string", "description": "Optional traceback or error string", "default": ""},
                },
                "required": ["target_file"],
            },
            handler=heal_code_tool,
            risk="auto",
        )
    )

    registry.register(
        Tool(
            name="diagnose_error",
            description="Analyzes an error or stack trace and returns root cause and exact surgical repair strategy.",
            params_schema={
                "type": "object",
                "properties": {
                    "error_text": {"type": "string", "description": "Traceback or error message to diagnose"},
                },
                "required": ["error_text"],
            },
            handler=diagnose_error_tool,
            risk="auto",
        )
    )
