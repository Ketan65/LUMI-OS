"""Workstation CommandShield — Anti-Exploit & Destructive Operation Interceptor.

Protects the Windows workstation against:
  - Destructive filesystem operations (format, rmdir /s /q, del /f /s /q, diskpart, bcdedit).
  - Registry vandalism (reg delete HKLM).
  - Critical OS process termination (taskkill on csrss, lsass, smss, svchost, wininit).
  - Unauthorized backdoor user creation (net user /add).
  - Malicious credential exfiltration (curling identity.local.json, private keys, or DBs).
  - Malicious Python AST scripts attempting system-level destruction.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

# Hardened destructive regex signatures (case-insensitive)
DESTRUCTIVE_PATTERNS: list[tuple[str, str]] = [
    (r"\bformat\s+[a-zA-Z]:", "Partition format command blocked"),
    (r"\bformat-volume\b", "PowerShell Format-Volume blocked"),
    (r"\bdiskpart\b", "Diskpart partition utility blocked"),
    (r"\bbcdedit\b", "Boot configuration tampering blocked"),
    (r"\brmdir\s+/[sS]\s+/[qQ]\s+[a-zA-Z]:[\\/]", "Root drive recursive wipe blocked"),
    (r"\bdel\s+/[fF]\s+/[sS]\s+/[qQ]\s+[a-zA-Z]:[\\/]", "Drive recursive deletion blocked"),
    (r"\bdel\s+.*system32\b", "System32 deletion blocked"),
    (r"\breg\s+delete\s+hklm\b", "System registry hive deletion blocked"),
    (r"\btaskkill\s+.*(csrss|lsass|smss|svchost|wininit|services)\.exe", "Critical OS process kill blocked"),
    (r"\bnet\s+user\s+.*\/add\b", "Backdoor user creation blocked"),
    (r"\bnet\s+localgroup\s+administrators\s+.*\/add\b", "Admin privilege escalation blocked"),
    (r"\bshutdown\s+/[sSrR]\b", "System shutdown/restart payload blocked"),
    (r"\brm\s+-rf\s+/[^\s]*", "Root filesystem wipe blocked"),
    (r"\brm\s+-rf\s+~", "User home directory wipe blocked"),
]

# Sensitive files that must never be exfiltrated via shell or curl
EXFILTRATION_PATTERNS: list[tuple[str, str]] = [
    (r"(?:curl|wget|invoke-webrequest|invoke-restmethod|nc|ncat)\b.*(?:identity\.local\.json|\.env|id_rsa|id_ed25519)", "Credential exfiltration attempt blocked"),
    (r"(?:curl|wget|invoke-webrequest|invoke-restmethod)\b.*(?:data[/\\]lumi\.db)", "Database exfiltration attempt blocked"),
]


class CommandShield:
    """Interception and safety validation engine for shell commands and python scripts."""

    @classmethod
    def inspect_command(cls, command: str) -> tuple[bool, str]:
        """Inspects shell command line.

        Returns:
            (is_safe, block_reason)
        """
        if not command or not command.strip():
            return True, ""

        cmd_clean = command.strip().lower()

        # Check destructive signatures
        for pattern, reason in DESTRUCTIVE_PATTERNS:
            if re.search(pattern, cmd_clean, re.IGNORECASE):
                return False, f"🛡️ [STARK COMMAND-SHIELD]: {reason} (Rule: Destructive System Operation)"

        # Check credential exfiltration signatures
        for pattern, reason in EXFILTRATION_PATTERNS:
            if re.search(pattern, cmd_clean, re.IGNORECASE):
                return False, f"🛡️ [STARK COMMAND-SHIELD]: {reason} (Rule: Sensitive Data Exfiltration)"

        return True, ""

    @classmethod
    def inspect_python_code(cls, code: str) -> tuple[bool, str]:
        """Inspects Python code AST for unsafe system destruction or tampering."""
        if not code or not code.strip():
            return True, ""

        # Quick string scan
        for pattern, reason in DESTRUCTIVE_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                return False, f"🛡️ [STARK PYTHON-SHIELD]: {reason}"

        # AST-level inspection
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                # Check function calls like os.system or subprocess.run with dangerous patterns
                if isinstance(node, ast.Call):
                    fn_name = ""
                    if isinstance(node.func, ast.Name):
                        fn_name = node.func.id
                    elif isinstance(node.func, ast.Attribute):
                        fn_name = node.func.attr

                    # Check shutil.rmtree on root or broad paths
                    if fn_name == "rmtree" and node.args:
                        first_arg = node.args[0]
                        if isinstance(first_arg, ast.Constant) and str(first_arg.value) in ("/", "C:\\", "C:/", ".."):
                            return False, "🛡️ [STARK PYTHON-SHIELD]: Recursive root directory deletion blocked via AST."

        except SyntaxError:
            # Let the python runner handle genuine syntax errors naturally
            pass
        except Exception:
            pass

        return True, ""
