"""Ollama Circuit Breaker & Self-Healing Neural Watchdog.

Protects LUMI from unhandled Ollama crashes, timeouts, or freezes:
  - Actively probes Ollama health endpoint (127.0.0.1:11434/api/tags).
  - Automatically attempts a non-blocking background spawn of `ollama serve` if down.
  - Transparently waits for warm-up and retries inference.
  - Delivers a structured, tactical failover notice instead of throwing a 500 error.
"""

from __future__ import annotations

import os
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")


class OllamaCircuitBreaker:
    """Monitors Ollama health and performs automatic recovery."""

    @classmethod
    def ping_ollama(cls, host: str = DEFAULT_OLLAMA_HOST, timeout: float = 1.5) -> bool:
        """Pings the Ollama local API server."""
        url = f"{host.rstrip('/')}/api/tags"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "LUMI-CircuitBreaker/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return res.status == 200
        except Exception:
            return False

    @classmethod
    def is_process_running(cls, process_name: str = "ollama") -> bool:
        """Checks whether the Ollama binary process is currently active."""
        try:
            import psutil
            for proc in psutil.process_iter(["name"]):
                name = str(proc.info.get("name") or "").lower()
                if process_name in name:
                    return True
        except Exception:
            pass
        return False

    @classmethod
    def attempt_auto_heal(cls, host: str = DEFAULT_OLLAMA_HOST, wait_timeout: float = 4.0) -> bool:
        """Attempts to revive a dead Ollama instance."""
        if cls.ping_ollama(host):
            return True

        # If process is completely missing, attempt background spawn
        if not cls.is_process_running("ollama"):
            try:
                # Windows background spawn without popping terminal window
                startupinfo = None
                if os.name == "nt":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = 0  # SW_HIDE

                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    startupinfo=startupinfo,
                    shell=False,
                )
            except Exception:
                pass

        # Poll for readiness
        deadline = time.time() + wait_timeout
        while time.time() < deadline:
            time.sleep(0.5)
            if cls.ping_ollama(host):
                return True

        return False

    @classmethod
    def format_failover_message(cls) -> str:
        """User-facing tactical Stark persona message on unrecoverable Ollama failure."""
        return (
            "⚠️ **[STARK NEURAL CIRCUIT-BREAKER]**: Local Ollama neural server (`127.0.0.1:11434`) "
            "is currently unreachable or initializing. Auto-recovery background pulse has been dispatched.\n\n"
            "**Recommended Diagnostic:**\n"
            "1. Verify `ollama serve` is running in your terminal.\n"
            "2. Ensure models (`hermes3:latest`, `qwen3:8b`) are downloaded via `ollama list`.\n"
            "3. Check GPU VRAM headroom in Windows Task Manager."
        )
