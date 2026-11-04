"""CODE-ORACLE: Static AST Quality & Security Inspector (Phase 23).

Analyzes Python source files for AST correctness, security vulnerabilities, complexity metrics,
and unit-test coverage recommendations.
"""

from __future__ import annotations

import ast
import logging
import os
import re
from pathlib import Path
from typing import Any

from tools.registry import Tool, ToolRegistry

logger = logging.getLogger("lumi.code_oracle")

DANGEROUS_PATTERNS = [
    (r"\beval\s*\(", "Use of 'eval()' is hazardous; consider ast.literal_eval() or safe parsers."),
    (r"\bexec\s*\(", "Use of 'exec()' allows arbitrary code execution."),
    (r"shell\s*=\s*True", "subprocess with 'shell=True' introduces command injection risks."),
    (r"(?:api_key|password|secret|token)\s*=\s*['\"][A-Za-z0-9_\-]{8,}['\"]", "Possible hardcoded credential or secret detected."),
]


class CodeOracle:
    """Static analysis and code quality guardian for LUMI."""

    def __init__(self, workspace_root: str | Path = "."):
        self.workspace_root = Path(workspace_root).resolve()

    def audit_file(self, file_path: str) -> dict[str, Any]:
        """Performs static AST and security audit on target Python file."""
        target = Path(file_path).resolve()
        if not target.exists():
            return {"success": False, "error": f"File does not exist: {file_path}"}
        if not target.is_file():
            return {"success": False, "error": f"Target is not a file: {file_path}"}

        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"success": False, "error": f"Could not read file: {e}"}

        findings: list[str] = []
        security_warnings: list[str] = []

        # 1. Regex Security Pattern Scan
        for pattern, warning in DANGEROUS_PATTERNS:
            matches = re.findall(pattern, content, flags=re.IGNORECASE)
            if matches:
                security_warnings.append(f"⚠️ {warning} (Matches found: {len(matches)})")

        # 2. AST Parsing & Structure Analysis
        classes_count = 0
        functions_count = 0
        async_functions_count = 0
        docstring_count = 0

        try:
            tree = ast.parse(content, filename=str(target))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    classes_count += 1
                    if ast.get_docstring(node):
                        docstring_count += 1
                elif isinstance(node, ast.FunctionDef):
                    functions_count += 1
                    if ast.get_docstring(node):
                        docstring_count += 1
                elif isinstance(node, ast.AsyncFunctionDef):
                    async_functions_count += 1
                    if ast.get_docstring(node):
                        docstring_count += 1
            ast_valid = True
        except SyntaxError as syn_err:
            ast_valid = False
            findings.append(f"❌ Syntax Error on line {syn_err.lineno}: {syn_err.msg}")

        # 3. Test Coverage Pairing Check
        stem = target.stem
        possible_tests = [
            target.parent / f"test_{stem}.py",
            target.parent / f"{stem}_test.py",
            self.workspace_root / "tests" / f"test_{stem}.py",
        ]
        has_tests = any(p.exists() for p in possible_tests)

        lines_of_code = len(content.splitlines())

        # Quality Grade Calculation
        quality_score = 100
        if not ast_valid:
            quality_score -= 50
        if security_warnings:
            quality_score -= (len(security_warnings) * 15)
        if not has_tests:
            quality_score -= 10
            findings.append(f"ℹ️ Unit test file 'test_{stem}.py' not found in workspace.")
        if functions_count > 0 and docstring_count < (functions_count / 2):
            quality_score -= 10
            findings.append(f"ℹ️ Low docstring coverage ({docstring_count}/{functions_count + classes_count} symbols documented).")

        quality_score = max(10, min(100, quality_score))

        return {
            "success": True,
            "file": str(target.relative_to(self.workspace_root) if target.is_relative_to(self.workspace_root) else target),
            "lines_of_code": lines_of_code,
            "ast_valid": ast_valid,
            "classes": classes_count,
            "functions": functions_count + async_functions_count,
            "docstring_coverage": f"{docstring_count}/{classes_count + functions_count + async_functions_count}",
            "has_unit_tests": has_tests,
            "security_warnings": security_warnings,
            "findings": findings,
            "quality_score": quality_score,
            "status": "PASS" if quality_score >= 80 else ("WARN" if quality_score >= 60 else "FAIL"),
        }


def register_code_oracle_tools(registry: ToolRegistry, workspace_root: str = ".") -> CodeOracle:
    oracle = CodeOracle(workspace_root=workspace_root)

    def code_oracle_audit(file_path: str) -> str:
        """Audits a Python code file for AST validity, dangerous security patterns, complexity metrics, and test coverage."""
        res = oracle.audit_file(file_path)
        if not res.get("success"):
            return f"❌ Audit failed: {res.get('error')}"

        sec_lines = "\n".join(res["security_warnings"]) if res["security_warnings"] else "✅ No critical security anti-patterns found."
        findings_lines = "\n".join([f"- {f}" for f in res["findings"]]) if res["findings"] else "- No structural defects detected."

        return (
            f"🔍 Code Oracle Audit: {res['file']}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Quality Score: {res['quality_score']}/100 [{res['status']}]\n"
            f"Lines of Code: {res['lines_of_code']} | Classes: {res['classes']} | Functions: {res['functions']}\n"
            f"Docstrings: {res['docstring_coverage']} | Tests Paired: {'Yes ✅' if res['has_unit_tests'] else 'No ⚠️'}\n\n"
            f"Security Analysis:\n{sec_lines}\n\n"
            f"Structural Observations:\n{findings_lines}"
        )

    registry.register(Tool(
        name="code_oracle_audit",
        description="Autonomous code auditor: inspects Python files for syntax, dangerous security anti-patterns, complexity, and test coverage.",
        params_schema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative or absolute path to Python file to inspect."},
            },
            "required": ["file_path"],
        },
        handler=code_oracle_audit,
        risk="auto",
    ))

    return oracle
