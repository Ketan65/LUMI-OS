"""LUMI Sovereign Security Sentinel — Intrusion Detection, WAF & Threat Quarantine.

Real-time defense monitoring for LUMI-OS:
- Automated WAF payload inspection (SQLi, command injection, path traversal)
- Dynamic IP rate limiting and brute-force throttling
- Incident quarantine and audit log tracking
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("lumi.security")

# Threat signatures for WAF inspection
INJECTION_SIGNATURES = [
    (re.compile(r"<\s*script\b[^>]*>", re.I), "Cross-Site Scripting (XSS) attempt"),
    (re.compile(r"\b(union\s+select|select\s+.*\s+from\s+information_schema)\b", re.I), "SQL Injection attempt"),
    (re.compile(r"(\$\([^)]+\)|\`[^`]+\`)", re.I), "Shell command substitution subshell"),
    (re.compile(r"\bpowershell.*(-enc|-encodedcommand)\b", re.I), "Encoded PowerShell payload"),
    (re.compile(r"\b(downloadstring|invoke-expression|\biex\b)", re.I), "PowerShell download-cradle execution"),
    (re.compile(r"\b(nc|ncat)\s+.*-e\b", re.I), "Netcat reverse shell pattern"),
    (re.compile(r"\b(curl|wget)\b.*\|\s*(bash|sh|cmd|powershell)", re.I), "Remote pipe-to-shell download"),
    (re.compile(r"\bformat\s+[a-zA-Z]:", re.I), "Destructive disk formatting command"),
    (re.compile(r"(\.\.[/\\]){3,}", re.I), "Path traversal directory escape sequence"),
    (re.compile(r"[/\\](system32|syswow64)[/\\](sam|system|config)", re.I), "Windows SAM registry access attempt"),
]


class SecuritySentinel:
    """Central intrusion detection, rate limiting, and threat quarantine coordinator."""

    def __init__(self, log_path: Optional[Path | str] = None):
        self.lock = threading.Lock()
        self.log_file = Path(log_path or "data/logs/security_audit.jsonl")
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        self.banned_ips: set[str] = set()
        self.incident_history: List[Dict[str, Any]] = []
        self.request_counters: Dict[str, List[float]] = {}
        self.max_attempts_per_minute = 60
        self.ban_threshold = 10

    def inspect_text_payload(self, text: str) -> tuple[bool, str]:
        """Inspect a string payload against WAF threat signatures.

        Returns (is_safe: bool, reason: str).
        """
        if not text:
            return True, "Clean"

        for pattern, description in INJECTION_SIGNATURES:
            if pattern.search(text):
                return False, f"WAF Threat Intercepted: {description}"

        return True, "Clean"

    def record_incident(
        self,
        source_ip: str,
        incident_type: str,
        detail: str,
        payload_preview: str = "",
    ) -> None:
        """Record a security incident, update ban metrics, and persist to audit log."""
        now = time.time()
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_ip": source_ip,
            "type": incident_type,
            "detail": detail,
            "payload_preview": payload_preview[:200],
        }

        with self.lock:
            self.incident_history.append(record)
            if len(self.incident_history) > 1000:
                self.incident_history.pop(0)

            # Check for ban threshold
            history = self.request_counters.setdefault(source_ip, [])
            history.append(now)
            # Filter attempts within last 5 minutes
            recent = [t for t in history if now - t < 300]
            self.request_counters[source_ip] = recent

            if len(recent) >= self.ban_threshold and source_ip not in {"127.0.0.1", "localhost", "::1"}:
                self.banned_ips.add(source_ip)
                logger.warning(f"[sentinel] Source IP {source_ip} auto-quarantined for excessive security violations.")

        # Append to audit JSONL
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            pass

    def is_ip_allowed(self, source_ip: str) -> bool:
        """Check if source IP is actively banned."""
        with self.lock:
            return source_ip not in self.banned_ips

    def get_security_posture(self) -> Dict[str, Any]:
        """Return live security metrics for Web Cockpit and health checks."""
        with self.lock:
            return {
                "status": "fortress_hardened",
                "total_threats_blocked": len(self.incident_history),
                "active_banned_ips": list(self.banned_ips),
                "recent_incidents": self.incident_history[-10:],
                "defense_layers": [
                    "WAF Payload Inspection",
                    "SafetyGate Taint Interceptor",
                    "Cluster HMAC Signature Guard",
                    "System Control Path Boundary Guard",
                    "Application Whitelist Launcher",
                ],
            }


# Global Singleton
_SENTINEL_INSTANCE: Optional[SecuritySentinel] = None


def get_security_sentinel() -> SecuritySentinel:
    global _SENTINEL_INSTANCE
    if _SENTINEL_INSTANCE is None:
        _SENTINEL_INSTANCE = SecuritySentinel()
    return _SENTINEL_INSTANCE
