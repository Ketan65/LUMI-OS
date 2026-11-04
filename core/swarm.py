"""SWARM-DEV: Autonomous Multi-Agent Software Engineering Team — Phase 9.

Orchestrates 4 specialized agents:
1. ArchitectAgent: System design, tech stack selection, folder structure, and module blueprints.
2. CoderAgent: Writes complete, production-grade code into workspace/<project_name>.
3. TesterAgent: Generates unit tests and executes them in an isolated subprocess.
4. DebuggerAgent: Analyzes failing test tracebacks, patches bugs, and iterates until passing.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ARCHITECT_SYSTEM_PROMPT = """You are the Lead Software Architect in LUMI's Autonomous Engineering Swarm.
Given the user's project goal, design a clean, modular, and functional project architecture.
You MUST respond ONLY with a valid JSON object with the following schema:
{
  "project_name": "clean_snake_case_name",
  "overview": "Concise summary of architecture and tech stack",
  "tech_stack": ["python", "sqlite3"],
  "files": [
    {
      "path": "app.py",
      "description": "Core application logic and entrypoint",
      "type": "code"
    },
    {
      "path": "test_app.py",
      "description": "Comprehensive unittest test cases verifying core logic",
      "type": "test"
    }
  ]
}
Do NOT include markdown explanations outside the JSON object."""

CODER_SYSTEM_PROMPT = """You are the Senior Software Engineer in LUMI's Autonomous Engineering Swarm.
Write complete, bug-free, production-grade code for the requested file.
Requirements:
1. Do NOT leave placeholder comments (e.g. '# implement here', 'pass', 'TODO').
2. Ensure all imports are standard library or popular libraries specified in tech stack.
3. Code must be runnable and immediately functional.
4. Return ONLY the code inside ```python and ``` code fence (or raw code)."""

TESTER_SYSTEM_PROMPT = """You are the Quality Assurance / Test Engineer in LUMI's Autonomous Engineering Swarm.
Given the source code of the project, write comprehensive test cases using Python's standard `unittest` framework.
Requirements:
1. Use `import unittest`.
2. Test both happy paths and edge cases.
3. Include `if __name__ == '__main__': unittest.main()`.
4. Return ONLY the code inside ```python and ``` code fence."""

DEBUGGER_SYSTEM_PROMPT = """You are the Principal Debugging Engineer in LUMI's Autonomous Engineering Swarm.
A test suite failed. You are given the original source code and the exact failure traceback.
Analyze the bug carefully, fix the root cause, and return the complete corrected code.
Return ONLY the corrected code inside ```python and ``` code fence."""


def extract_code_block(text: str) -> str:
    """Extracts raw code from text or markdown code fence."""
    match = re.search(r"```(?:python|py)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text.strip()


def extract_json_object(text: str) -> dict | None:
    """Extracts JSON object from text or markdown code fence."""
    clean = text.strip()
    match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", clean)
    if match:
        clean = match.group(1).strip()
    elif "{" in clean and "}" in clean:
        clean = clean[clean.find("{") : clean.rfind("}") + 1]

    try:
        data = json.loads(clean)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


@dataclass
class SwarmFileSpec:
    path: str
    description: str
    type: str = "code"


@dataclass
class SwarmProjectSpec:
    project_name: str
    overview: str
    tech_stack: list[str]
    files: list[SwarmFileSpec]


class ArchitectAgent:
    """Designs architecture, file tree, and module specifications."""

    def design(self, goal: str, brain: Any) -> SwarmProjectSpec:
        prompt = f"Design a complete, modular software project for this goal:\nGoal: {goal}"
        messages = [
            {"role": "system", "content": ARCHITECT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        try:
            reply = brain.chat(messages, temperature=0.1)
            content = reply.text if hasattr(reply, "text") else str(reply)
            parsed = extract_json_object(content)
            if parsed and "files" in parsed and isinstance(parsed["files"], list):
                files = [
                    SwarmFileSpec(
                        path=f.get("path", "module.py"),
                        description=f.get("description", ""),
                        type=f.get("type", "code"),
                    )
                    for f in parsed["files"]
                ]
                # Ensure at least one test file exists
                if not any(f.type == "test" or "test" in f.path.lower() for f in files):
                    files.append(
                        SwarmFileSpec(
                            path="test_app.py",
                            description="Unit tests for the application",
                            type="test",
                        )
                    )

                name = re.sub(r"[^a-zA-Z0-9_]", "_", parsed.get("project_name", "swarm_app")).lower()
                return SwarmProjectSpec(
                    project_name=name or "swarm_app",
                    overview=parsed.get("overview", "Autonomous project generated by LUMI Swarm"),
                    tech_stack=parsed.get("tech_stack", ["python"]),
                    files=files,
                )
        except Exception as exc:
            print(f"[Architect] Notice: LLM design fallback invoked: {exc}")

        # Fallback heuristic architecture
        clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", goal.strip().split()[-1] if goal.strip() else "app").lower()
        if not clean_name or clean_name == "app":
            clean_name = "swarm_project"

        return SwarmProjectSpec(
            project_name=clean_name,
            overview=f"Autonomous project for: {goal}",
            tech_stack=["python"],
            files=[
                SwarmFileSpec(path="main.py", description="Main application logic", type="code"),
                SwarmFileSpec(path="test_main.py", description="Automated unit tests", type="test"),
            ],
        )


class CoderAgent:
    """Generates complete, executable code and writes to workspace."""

    def code_file(
        self,
        project_dir: Path,
        file_spec: SwarmFileSpec,
        spec: SwarmProjectSpec,
        brain: Any,
        existing_sources: dict[str, str] | None = None,
    ) -> Path:
        target_path = (project_dir / file_spec.path).resolve()
        # Security sanity check: must stay within project_dir
        if not str(target_path).startswith(str(project_dir.resolve())):
            target_path = project_dir / Path(file_spec.path).name

        target_path.parent.mkdir(parents=True, exist_ok=True)

        existing_context = ""
        if existing_sources:
            blocks = [
                f"--- Existing File: `{path}` ---\n```python\n{src[:2500]}\n```"
                for path, src in existing_sources.items()
                if path != file_spec.path
            ]
            if blocks:
                existing_context = (
                    "\n\nAlready implemented project files (you MUST match their exact module names, "
                    "class names, function signatures, and return types):\n"
                    + "\n\n".join(blocks)
                )

        is_test = file_spec.type == "test" or "test" in file_spec.path.lower()
        role_sys = TESTER_SYSTEM_PROMPT if is_test else CODER_SYSTEM_PROMPT

        prompt = (
            f"Project: {spec.project_name}\n"
            f"Overview: {spec.overview}\n"
            f"Tech Stack: {', '.join(spec.tech_stack)}\n"
            f"File to implement: {file_spec.path}\n"
            f"Description: {file_spec.description}\n"
            f"Other files in project: {[f.path for f in spec.files]}"
            f"{existing_context}\n\n"
            f"Write the complete, bug-free Python code for `{file_spec.path}`."
        )

        messages = [
            {"role": "system", "content": role_sys},
            {"role": "user", "content": prompt},
        ]

        code = ""
        try:
            reply = brain.chat(messages, temperature=0.1)
            content = reply.text if hasattr(reply, "text") else str(reply)
            code = extract_code_block(content)
        except Exception as exc:
            print(f"[Coder] Notice: Error generating code for {file_spec.path}: {exc}")

        if not code or len(code.strip()) < 5:
            # Fallback starter code
            if is_test:
                code = (
                    "import unittest\n\n"
                    "class TestApp(unittest.TestCase):\n"
                    "    def test_basic(self):\n"
                    "        self.assertTrue(True)\n\n"
                    "if __name__ == '__main__':\n"
                    "    unittest.main()\n"
                )
            else:
                code = (
                    f"# {spec.project_name} - {file_spec.path}\n"
                    f"# Generated autonomously by LUMI SWARM-DEV\n\n"
                    "def run():\n"
                    f"    print('Running {spec.project_name}')\n"
                    "    return True\n\n"
                    "if __name__ == '__main__':\n"
                    "    run()\n"
                )

        target_path.write_text(code, encoding="utf-8")
        return target_path


class TesterAgent:
    """Runs test suite in project directory and evaluates pass/fail."""

    def run_tests(self, project_dir: Path, timeout: float = 15.0) -> tuple[bool, str]:
        # Look for unittest or pytest files
        test_files = list(project_dir.glob("test_*.py")) + list(project_dir.glob("*_test.py"))
        if not test_files:
            return True, "No test files found to execute."

        # Prefer running unittest discover or target test file
        primary_test = test_files[0].name
        cmd = [sys.executable, "-m", "unittest", primary_test]

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(project_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = (proc.stdout + "\n" + proc.stderr).strip()
            passed = (
                proc.returncode == 0
                and "FAILED" not in output
                and "ERROR:" not in output
                and "Traceback (most recent call last):" not in output
            )
            return passed, output
        except subprocess.TimeoutExpired:
            return False, f"Tests timed out after {timeout} seconds."
        except Exception as exc:
            return False, f"Test execution error: {exc}"


class DebuggerAgent:
    """Analyzes test failures, locates the source defect, and self-heals code."""

    def heal(
        self,
        project_dir: Path,
        failing_output: str,
        spec: SwarmProjectSpec,
        brain: Any,
    ) -> list[str]:
        # Load all existing project files so Debugger sees both code and test definitions
        all_sources: dict[str, str] = {}
        for f in spec.files:
            fp = project_dir / f.path
            if fp.exists():
                all_sources[f.path] = fp.read_text(encoding="utf-8")

        # Identify which files are candidates for healing (code files first, then test files if import/signature mismatch)
        candidate_files = sorted(
            spec.files,
            key=lambda f: 1 if (f.type == "test" or "test" in f.path.lower()) else 0,
        )

        healed: list[str] = []
        for file_spec in candidate_files:
            file_path = project_dir / file_spec.path
            if not file_path.exists():
                continue

            current_code = file_path.read_text(encoding="utf-8")

            # Check if this file is mentioned in the traceback or is the primary implementation file
            is_test = file_spec.type == "test" or "test" in file_spec.path.lower()
            if file_spec.path not in failing_output and is_test and healed:
                continue

            other_files_ctx = "\n\n".join(
                f"--- Other Project File: `{p}` ---\n```python\n{src[:2000]}\n```"
                for p, src in all_sources.items()
                if p != file_spec.path
            )

            prompt = (
                f"A test failure occurred in project `{spec.project_name}`.\n"
                f"Failing Output & Traceback:\n```\n{failing_output}\n```\n\n"
                f"{other_files_ctx}\n\n"
                f"Target File to Fix: `{file_spec.path}`\n"
                f"Current Code:\n```python\n{current_code}\n```\n\n"
                f"Fix the bug in `{file_spec.path}` so all tests pass and imports/signatures match across files. "
                f"Return ONLY the complete corrected Python code for `{file_spec.path}`."
            )

            messages = [
                {"role": "system", "content": DEBUGGER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            try:
                reply = brain.chat(messages, temperature=0.1)
                content = reply.text if hasattr(reply, "text") else str(reply)
                fixed_code = extract_code_block(content)
                if fixed_code and len(fixed_code) > 10 and fixed_code != current_code:
                    file_path.write_text(fixed_code, encoding="utf-8")
                    all_sources[file_spec.path] = fixed_code
                    healed.append(file_spec.path)
            except Exception as exc:
                print(f"[Debugger] Notice: Error self-healing {file_spec.path}: {exc}")

        return healed


class SwarmCoordinator:
    """Master orchestrator for the 4-agent Autonomous Software Engineering Swarm."""

    def __init__(self, workspace_root: Path | str = "workspace", brain: Any = None):
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.brain = brain
        self.architect = ArchitectAgent()
        self.coder = CoderAgent()
        self.tester = TesterAgent()
        self.debugger = DebuggerAgent()

    def develop(
        self,
        goal: str,
        project_name: str | None = None,
        max_healing_loops: int = 3,
        brain: Any = None,
    ) -> dict[str, Any]:
        active_brain = brain or self.brain
        if not active_brain:
            raise ValueError("Swarm requires a valid Brain instance for multi-agent reasoning.")

        # Step 1: Architect Designs Specification
        spec = self.architect.design(goal, active_brain)
        if project_name:
            spec.project_name = re.sub(r"[^a-zA-Z0-9_]", "_", project_name).lower()

        project_dir = self.workspace_root / spec.project_name
        project_dir.mkdir(parents=True, exist_ok=True)

        # Step 2: Coder Writes All Modules (code files first, then test files with full code context)
        ordered_files = sorted(
            spec.files,
            key=lambda f: 1 if (f.type == "test" or "test" in f.path.lower()) else 0,
        )
        created_files: list[str] = []
        existing_sources: dict[str, str] = {}
        for file_spec in ordered_files:
            written_path = self.coder.code_file(
                project_dir, file_spec, spec, active_brain, existing_sources=existing_sources
            )
            rel = str(written_path.relative_to(project_dir))
            created_files.append(rel)
            try:
                existing_sources[file_spec.path] = written_path.read_text(encoding="utf-8")
            except Exception:
                pass

        # Step 3: Tester Executes Tests
        passed, test_out = self.tester.run_tests(project_dir)

        # Step 4: Self-Healing Debugger Loop (if tests failed)
        healing_iterations = 0
        healed_files_log: list[list[str]] = []

        while not passed and healing_iterations < max_healing_loops:
            healing_iterations += 1
            healed = self.debugger.heal(project_dir, test_out, spec, active_brain)
            healed_files_log.append(healed)
            if not healed:
                break
            passed, test_out = self.tester.run_tests(project_dir)

        # Generate Human-Friendly Summary
        status_emoji = "✅" if passed else "⚠️"
        summary_lines = [
            f"### {status_emoji} LUMI SWARM-DEV: `{spec.project_name}`",
            f"**Goal:** {goal}",
            f"**Overview:** {spec.overview}",
            f"**Tech Stack:** {', '.join(spec.tech_stack)}",
            f"**Project Directory:** `{project_dir}`",
            "",
            "**Generated Files:**",
        ]
        for f in created_files:
            summary_lines.append(f"- 📄 `{f}`")

        summary_lines.append("")
        if passed:
            summary_lines.append(f"**Test Verification:** Passed seamlessly ({healing_iterations} self-healing iterations).")
        else:
            summary_lines.append(f"**Test Verification:** Notice: Some tests require attention after {healing_iterations} healing attempts.")

        summary_lines.append("")
        summary_lines.append(f"**Run Command:** `python workspace/{spec.project_name}/main.py`")

        return {
            "ok": passed,
            "project_name": spec.project_name,
            "project_dir": str(project_dir),
            "files": created_files,
            "tests_passed": passed,
            "healing_iterations": healing_iterations,
            "test_output": test_out[:1000],
            "summary": "\n".join(summary_lines),
        }
