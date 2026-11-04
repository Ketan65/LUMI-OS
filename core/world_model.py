"""WORLD-MODEL: Counterfactual Pre-Flight Code Simulator & Atomic Patch Engine (Phase 27).

Allows LUMI to "think and simulate before acting" on code and system changes:
1. Ephemeral Shadow Sandbox: Clones target module + unit tests into an isolated temp workspace.
2. Three-Gate Pre-Flight Verification:
   - Gate 1: AST Syntax & Structural Validity
   - Gate 2: Cyber-Sentinel CWE Security Verification (Zero new vulnerabilities)
   - Gate 3: Subprocess Unit Test & Runtime Verification
3. Atomic Commit with Instant Rollback Snapshot: Only writes to disk if all 3 gates pass.
4. Runtime Memory & Latency Profiler (`tracemalloc` + `perf_counter` subprocess telemetry).
"""

from __future__ import annotations

import ast
import difflib
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from core.cyber_sentinel import CyberSentinel

logger = logging.getLogger("lumi.world_model")


class WorldModelSimulator:
    """Counterfactual pre-flight simulator and atomic code mutation engine."""

    def __init__(self, workspace_root: str | Path = "workspace", brain: Any = None):
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.backup_dir = self.workspace_root / ".shadow_backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.brain = brain
        self.sentinel = CyberSentinel(workspace_root=self.workspace_root, brain=brain)
        self.simulations_log: list[dict[str, Any]] = []

    def profile_code(self, code: str, timeout: float = 10.0) -> dict[str, Any]:
        """Profiles Python code in an isolated subprocess using tracemalloc and perf_counter."""
        harness = (
            "import json, time, tracemalloc, sys\n"
            "tracemalloc.start()\n"
            "t0 = time.perf_counter()\n"
            "ns = {'__name__': '__main__'}\n"
            f"code_str = {code!r}\n"
            "try:\n"
            "    exec(compile(code_str, '<world_model>', 'exec'), ns)\n"
            "    ok = True\n"
            "    err = ''\n"
            "except Exception as exc:\n"
            "    ok = False\n"
            "    err = f'{type(exc).__name__}: {exc}'\n"
            "elapsed_ms = round((time.perf_counter() - t0) * 1000, 3)\n"
            "current_b, peak_b = tracemalloc.get_traced_memory()\n"
            "tracemalloc.stop()\n"
            "print('__WM_METRICS__:' + json.dumps({\n"
            "    'ok': ok, 'error': err, 'elapsed_ms': elapsed_ms,\n"
            "    'peak_kb': round(peak_b / 1024.0, 2)\n"
            "}))\n"
        )
        try:
            proc = subprocess.run(
                [sys.executable, "-c", harness],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            stdout_lines = []
            metrics = {"ok": proc.returncode == 0, "error": proc.stderr.strip(), "elapsed_ms": 0.0, "peak_kb": 0.0}
            for ln in proc.stdout.splitlines():
                if ln.startswith("__WM_METRICS__:"):
                    try:
                        metrics = json.loads(ln.split("__WM_METRICS__:", 1)[1])
                    except Exception:
                        pass
                else:
                    stdout_lines.append(ln)
            metrics["stdout"] = "\n".join(stdout_lines).strip()
            return metrics
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"Execution timed out after {timeout}s", "elapsed_ms": timeout * 1000, "peak_kb": 0.0, "stdout": ""}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "elapsed_ms": 0.0, "peak_kb": 0.0, "stdout": ""}

    def simulate_and_commit(
        self,
        file_path: str | Path,
        candidate_code: str | None = None,
        optimization_goal: str | None = None,
        commit_if_passed: bool = True,
    ) -> dict[str, Any]:
        """Simulates a code change in an isolated shadow sandbox and atomically commits only if all 3 gates pass."""
        t0 = time.perf_counter()
        target = Path(file_path).resolve()
        if not target.exists():
            # Try relative to workspace_root
            alt = (self.workspace_root / file_path).resolve()
            if alt.exists():
                target = alt
            else:
                return {"success": False, "error": f"Target file not found: {file_path}"}

        original_code = target.read_text(encoding="utf-8", errors="replace")

        # If candidate_code not explicitly provided, synthesize via LLM from optimization_goal
        if not candidate_code and optimization_goal and self.brain is not None:
            try:
                prompt = (
                    f"Target File (`{target.name}`):\n```python\n{original_code}\n```\n\n"
                    f"Optimization / Refactoring Goal: {optimization_goal}\n\n"
                    "Produce the complete, improved Python code preserving all public function/class signatures. "
                    "Return ONLY the code inside ```python and ```."
                )
                rep = self.brain.chat(
                    [
                        {"role": "system", "content": "You are LUMI's Counterfactual World-Model Optimizer. Output valid Python code only."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                )
                txt = rep.text if hasattr(rep, "text") else str(rep)
                m = re.search(r"```(?:python|py)?\s*([\s\S]*?)\s*```", txt)
                candidate_code = m.group(1).strip() if m else txt.strip()
            except Exception as exc:
                return {"success": False, "error": f"LLM candidate generation failed: {exc}"}

        if not candidate_code:
            return {"success": False, "error": "Either candidate_code or optimization_goal must be provided."}

        # Gate 1: AST Syntax Verification
        try:
            ast.parse(candidate_code, filename=target.name)
            gate1_ast = {"passed": True, "message": "AST syntax valid."}
        except SyntaxError as syn_err:
            gate1_ast = {"passed": False, "message": f"SyntaxError at line {syn_err.lineno}: {syn_err.msg}"}

        # Gate 2: Cyber-Sentinel CWE Security Check
        sec_scan = self.sentinel.deep_scan_code(candidate_code, filename=target.name)
        gate2_security = {
            "passed": sec_scan["vulnerabilities_count"] == 0 and sec_scan["ast_valid"],
            "security_score": sec_scan["security_score"],
            "vulnerabilities_count": sec_scan["vulnerabilities_count"],
            "verdict": sec_scan["verdict"],
        }

        # Gate 3: Shadow Sandbox Execution & Companion Test Suite
        gate3_runtime = {"passed": False, "output": "", "elapsed_ms": 0.0}
        if gate1_ast["passed"] and gate2_security["passed"]:
            with tempfile.TemporaryDirectory(prefix="lumi_shadow_") as tmp_dir:
                shadow_dir = Path(tmp_dir)
                # Copy all .py files in target's parent directory so local imports & test_*.py work
                for py_file in target.parent.glob("*.py"):
                    try:
                        shutil.copy2(py_file, shadow_dir / py_file.name)
                    except Exception:
                        pass

                # Write candidate code into shadow target
                shadow_target = shadow_dir / target.name
                shadow_target.write_text(candidate_code, encoding="utf-8")

                # Check if companion unit test exists
                companion_tests = [
                    shadow_dir / f"test_{target.stem}.py",
                    shadow_dir / f"{target.stem}_test.py",
                ]
                existing_test = next((t for t in companion_tests if t.exists()), None)

                rt0 = time.perf_counter()
                try:
                    if existing_test is not None:
                        cmd = [sys.executable, "-m", "unittest", existing_test.name]
                    else:
                        cmd = [sys.executable, shadow_target.name]

                    proc = subprocess.run(
                        cmd,
                        cwd=str(shadow_dir),
                        capture_output=True,
                        text=True,
                        timeout=10.0,
                    )
                    out = (proc.stdout + "\n" + proc.stderr).strip()
                    passed = proc.returncode == 0 and "Traceback (most recent call last):" not in out
                    gate3_runtime = {
                        "passed": passed,
                        "mode": f"unittest ({existing_test.name})" if existing_test else "direct_execution",
                        "output": out[:800],
                        "elapsed_ms": round((time.perf_counter() - rt0) * 1000, 2),
                    }
                except Exception as exc:
                    gate3_runtime = {
                        "passed": False,
                        "mode": "error",
                        "output": str(exc),
                        "elapsed_ms": round((time.perf_counter() - rt0) * 1000, 2),
                    }

        all_gates_passed = gate1_ast["passed"] and gate2_security["passed"] and gate3_runtime["passed"]
        committed = False
        backup_path = ""

        if all_gates_passed and commit_if_passed and candidate_code != original_code:
            ts = int(time.time())
            bpath = self.backup_dir / f"{target.stem}_{ts}.bak.py"
            bpath.write_text(original_code, encoding="utf-8")
            backup_path = str(bpath)
            target.write_text(candidate_code, encoding="utf-8")
            committed = True

        diff_text = "\n".join(
            difflib.unified_diff(
                original_code.splitlines(),
                candidate_code.splitlines(),
                fromfile=f"before/{target.name}",
                tofile=f"after/{target.name}",
                lineterm="",
            )
        )

        result = {
            "success": True,
            "file": str(target),
            "verdict": "COMMIT_APPROVED" if all_gates_passed else "REJECTED_SAFE_ROLLBACK",
            "committed": committed,
            "backup_path": backup_path,
            "gates": {
                "gate1_ast": gate1_ast,
                "gate2_security": gate2_security,
                "gate3_runtime": gate3_runtime,
            },
            "diff": diff_text,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        self.simulations_log.append(result)
        return result
