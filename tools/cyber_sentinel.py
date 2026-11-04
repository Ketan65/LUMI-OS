"""Tool bindings for LUMI Cyber-Sentinel (Phase 25: Autonomous VAPT & Auto-Remediation Cortex)."""

from __future__ import annotations

from typing import Any

from core.cyber_sentinel import CyberSentinel
from tools.registry import Tool, ToolRegistry


def register_cyber_sentinel_tools(
    registry: ToolRegistry,
    workspace_root: str = ".",
    brain: Any = None,
) -> CyberSentinel:
    sentinel = CyberSentinel(workspace_root=workspace_root, brain=brain)

    def vapt_deep_scan(file_path: str) -> str:
        """Performs deep AST taint & CWE/CVSS v3.1 vulnerability analysis on a Python source file."""
        res = sentinel.deep_scan_file(file_path)
        if not res.get("success"):
            return f"❌ VAPT Scan Error: {res.get('error')}"

        lines = [
            f"### 🛡️ SENTINEL/LUMI VAPT Deep Scan: `{res['file']}`",
            f"**Verdict:** `{res['verdict']}` | **Security Score:** `{res['security_score']}/100` | **Max CVSS:** `{res['max_cvss']}`",
            f"**AST Valid:** `{res['ast_valid']}` | **Scan Time:** `{res['elapsed_ms']}ms`",
            "",
        ]
        vulns = res.get("vulnerabilities", [])
        if not vulns:
            lines.append("✅ **Zero CWE vulnerabilities or taint flows detected. File is FORTIFIED.**")
        else:
            lines.append(f"**⚠️ Detected Vulnerabilities ({len(vulns)}):**")
            for v in vulns:
                lines.append(
                    f"- **[{v['cwe_id']} | {v['severity']} | CVSS {v['cvss_score']}] Line {v['line']}:** {v['title']}\n"
                    f"  - *Code:* `{v['code_snippet']}`\n"
                    f"  - *Taint Flow:* {v['taint_flow']}\n"
                    f"  - *Fix:* {v['remediation']}"
                )
        return "\n".join(lines)

    def vapt_auto_patch(file_path: str) -> str:
        """Autonomously patches all detected CWE vulnerabilities in a Python file and verifies remediation."""
        res = sentinel.auto_patch_file(file_path, write_in_place=True)
        if not res.get("success"):
            return f"❌ Auto-Patch Failed: {res.get('error')}"
        if not res.get("patched"):
            return f"✅ `{res['file']}` is already fortified (Score: {res.get('pre_score', 100)}/100)."

        diff_preview = res.get("diff", "")[:1500]
        return (
            f"### 🔧 Autonomous Security Patch Applied: `{res['file']}`\n"
            f"- **Pre-Patch CWEs:** `{res['pre_vulnerabilities']}` (Score: `{res['pre_score']}/100`)\n"
            f"- **Post-Patch CWEs:** `{res['post_vulnerabilities']}` (Score: `{res['post_score']}/100` — `{res['post_verdict']}`)\n\n"
            f"**Unified Security Diff:**\n```diff\n{diff_preview}\n```"
        )

    def vapt_surface_audit() -> str:
        """Audits active listening TCP sockets and local network attack surface on Boss's workstation."""
        res = sentinel.audit_attack_surface()
        lines = [
            f"### 📡 Workstation Attack Surface & Port Audit",
            f"**Cyber Posture Score:** `{res['posture_score']}/100` | **Total Listening Sockets:** `{res['total_listening_sockets']}`",
            f"**Loopback-Isolated:** `{res['loopback_bound_count']}` | **LAN/Wildcard Exposed Ports:** `{res['lan_exposed_ports']}`",
            "",
            "**Active Listeners (Top 15):**",
        ]
        for l in res["listeners"][:15]:
            badge = "🟢" if l["exposure"] == "LOOPBACK_ONLY" else "🟠"
            lines.append(f"- {badge} `{l['ip']}:{l['port']}` — Process: **{l['process']}** (`{l['exposure']}`)")
        return "\n".join(lines)

    registry.register(
        Tool(
            name="vapt_deep_scan",
            description="Performs SENTINEL-grade AST taint & CWE/CVSS v3.1 security vulnerability scan on a Python file.",
            params_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the Python file to scan"},
                },
                "required": ["file_path"],
            },
            handler=vapt_deep_scan,
            risk="auto",
        )
    )

    registry.register(
        Tool(
            name="vapt_auto_patch",
            description="Autonomously patches CWE security vulnerabilities in a Python file, verifies AST & zero-CWE status, and returns a unified diff.",
            params_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the vulnerable Python file to auto-remediate"},
                },
                "required": ["file_path"],
            },
            handler=vapt_auto_patch,
            risk="auto",
        )
    )

    registry.register(
        Tool(
            name="vapt_surface_audit",
            description="Audits local listening TCP ports, process bindings, and LAN exposure posture on the workstation.",
            params_schema={"type": "object", "properties": {}},
            handler=vapt_surface_audit,
            risk="auto",
        )
    )

    return sentinel
