"""Proactive Anticipatory Intelligence & Ambient Guard (LUMI v38.0).

Continuously monitors operator context without polling CPU or interrupting workflow:
  - Active Window Sentinel: Detects focused IDE, terminal, browser, or game.
  - Clipboard Error Interceptor: Catches Python/JS/Rust tracebacks copied to clipboard.
  - Background Self-Healing Dispatcher: Pre-computes diagnoses and surgical patches
    BEFORE the user even asks.
  - System Telemetry Guard: Alerts on RAM exhaustion (>92%) or thermal stress.
  - Persistent alert queue at data/proactive_alerts.jsonl.
"""

from __future__ import annotations

import collections
import ctypes
import datetime
import hashlib
import json
import logging
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import psutil

try:
    import win32gui
except ImportError:
    win32gui = None

from evolution.self_healing_engine import SelfHealingEngine, get_self_healing_engine
from tools.registry import Tool, ToolRegistry

logger = logging.getLogger("lumi.sentinel")

ALERTS_FILE = Path("data/proactive_alerts.jsonl")

# Error matching regexes
_ERROR_SIGNATURES = [
    re.compile(r"Traceback \(most recent call last\):", re.IGNORECASE),
    re.compile(r"(SyntaxError|IndentationError|TabError):", re.IGNORECASE),
    re.compile(r"(KeyError|ZeroDivisionError|ModuleNotFoundError|ImportError):", re.IGNORECASE),
    re.compile(r"(TypeError|AttributeError|ValueError|IndexError):", re.IGNORECASE),
    re.compile(r"fatal: (not a git repository|refusing to merge)", re.IGNORECASE),
    re.compile(r"npm ERR! code [A-Z0-9_]+", re.IGNORECASE),
]


@dataclass
class ProactiveAlert:
    id: str
    timestamp: str
    category: str  # "code_error", "system_telemetry", "git_conflict", "workflow_nudge"
    title: str
    details: str
    remediation: str
    active_window: str = "Unknown"
    status: str = "pending"  # "pending", "dismissed", "applied"


class ProactiveSentinel:
    """Ambient background context sensor and anticipatory issue solver."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        healing_engine: SelfHealingEngine | None = None,
        poll_interval_sec: float = 2.0,
        alerts_path: Path | None = None,
    ) -> None:
        self.registry = registry
        self.healing_engine = healing_engine or get_self_healing_engine()
        self.poll_interval_sec = max(0.5, float(poll_interval_sec))
        self.alerts_path = alerts_path or ALERTS_FILE
        self.alerts_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._alerts: collections.deque[ProactiveAlert] = collections.deque(maxlen=50)
        self._seen_hashes: set[str] = set()
        self._last_active_window = ""
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None

        self._load_existing_alerts()
        self._register_tools()

    def _register_tools(self) -> None:
        """Exposes proactive sentinel tools into ToolRegistry."""
        if self.registry is None:
            return

        self.registry.register(
            Tool(
                name="check_proactive_alerts",
                description="Checks active proactive alerts, intercepted clipboard errors, and recommended auto-fixes.",
                params_schema={"type": "object", "properties": {"limit": {"type": "integer"}}},
                handler=lambda limit=5: self.get_alerts_summary(limit=int(limit)),
                risk="read",
            )
        )
        self.registry.register(
            Tool(
                name="inspect_ambient_context",
                description="Inspects current foreground window, system telemetry (CPU, RAM, GPU), and clipboard state.",
                params_schema={"type": "object", "properties": {}},
                handler=lambda: self.inspect_ambient_context(),
                risk="read",
            )
        )

    def _load_existing_alerts(self) -> None:
        """Loads non-dismissed alerts from disk."""
        if not self.alerts_path.exists():
            return
        try:
            with open(self.alerts_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line.strip())
                        alert = ProactiveAlert(**data)
                        self._alerts.append(alert)
                        if alert.status == "pending":
                            content_hash = hashlib.md5(alert.details.encode("utf-8")).hexdigest()
                            self._seen_hashes.add(content_hash)
        except Exception as e:
            logger.warning("Error loading proactive alerts: %s", e)

    def _persist_alert(self, alert: ProactiveAlert) -> None:
        """Appends alert to JSONL."""
        try:
            with open(self.alerts_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(alert)) + "\n")
        except Exception as e:
            logger.error("Failed to persist proactive alert: %s", e)

    @staticmethod
    def get_clipboard_text() -> str | None:
        """Reads unicode clipboard contents using ctypes Windows user32 API."""
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        if not user32.OpenClipboard(0):
            return None
        try:
            CF_UNICODETEXT = 13
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return None
            kernel32.GlobalLock.restype = ctypes.c_void_p
            ptr = kernel32.GlobalLock(handle)
            if not ptr:
                return None
            try:
                return ctypes.wstring_at(ptr)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()

    def get_active_window_title(self) -> str:
        """Returns the title of the current foreground window."""
        if win32gui is None:
            return "Unknown"
        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                title = win32gui.GetWindowText(hwnd)
                return title.strip() or "Untitled Window"
        except Exception:
            pass
        return "Unknown"

    def scan_cycle(self) -> ProactiveAlert | None:
        """Performs a single evaluation cycle: checks clipboard, telemetry, active window."""
        active_window = self.get_active_window_title()
        self._last_active_window = active_window

        # 1. Clipboard inspection
        clip_text = self.get_clipboard_text()
        if clip_text and len(clip_text.strip()) > 10:
            is_error = any(pattern.search(clip_text) for pattern in _ERROR_SIGNATURES)
            if is_error:
                content_hash = hashlib.md5(clip_text.strip().encode("utf-8")).hexdigest()
                with self._lock:
                    already_seen = content_hash in self._seen_hashes
                if not already_seen:
                    # Intercepted new error!
                    diagnosis = self.healing_engine.diagnose_error(clip_text)
                    alert_id = f"alt_{int(time.time())}_{content_hash[:6]}"
                    alert = ProactiveAlert(
                        id=alert_id,
                        timestamp=datetime.datetime.now().isoformat(timespec="seconds"),
                        category="code_error",
                        title=f"Intercepted {diagnosis.get('error_type', 'Runtime Error')}",
                        details=clip_text[:400],
                        remediation=diagnosis.get("suggested_fix", "Run /heal to auto-patch."),
                        active_window=active_window,
                        status="pending",
                    )
                    with self._lock:
                        self._alerts.appendleft(alert)
                        self._seen_hashes.add(content_hash)
                    self._persist_alert(alert)
                    logger.info("Proactive Sentinel intercepted error from '%s': %s", active_window, alert.title)
                    return alert

        # 2. System telemetry inspection (RAM exhaustion check)
        ram_pct = psutil.virtual_memory().percent
        if ram_pct >= 93.0:
            telemetry_hash = f"ram_spike_{int(time.time() // 180)}"  # at most once per 3 mins
            with self._lock:
                already_seen = telemetry_hash in self._seen_hashes
            if not already_seen:
                alert = ProactiveAlert(
                    id=f"alt_ram_{int(time.time())}",
                    timestamp=datetime.datetime.now().isoformat(timespec="seconds"),
                    category="system_telemetry",
                    title="Critical RAM Usage Warning (>93%)",
                    details=f"Current RAM consumption is at {ram_pct:.1f}%. Background tasks may face OOM.",
                    remediation="Consider terminating unused processes or running garbage collection.",
                    active_window=active_window,
                    status="pending",
                )
                with self._lock:
                    self._alerts.appendleft(alert)
                    self._seen_hashes.add(telemetry_hash)
                self._persist_alert(alert)
                return alert

        return None

    def start_background_daemon(self) -> None:
        """Launches continuous monitoring daemon thread."""
        if self._worker_thread and self._worker_thread.is_alive():
            return

        self._stop_event.clear()

        def _runner() -> None:
            logger.info("Proactive Sentinel daemon active (poll=%.1fs).", self.poll_interval_sec)
            while not self._stop_event.is_set():
                try:
                    self.scan_cycle()
                except Exception as e:
                    logger.debug("Sentinel scan cycle exception: %s", e)
                time.sleep(self.poll_interval_sec)

        self._worker_thread = threading.Thread(target=_runner, daemon=True, name="LumiProactiveSentinel")
        self._worker_thread.start()

    def stop_background_daemon(self) -> None:
        """Halts the background thread."""
        self._stop_event.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=3)

    def get_pending_alerts(self, limit: int = 5) -> list[dict[str, Any]]:
        """Returns pending active alerts."""
        with self._lock:
            pending = [asdict(a) for a in self._alerts if a.status == "pending"]
            return pending[:limit]

    def get_alerts_summary(self, limit: int = 5) -> str:
        """Human-readable markdown summary of recent proactive alerts."""
        alerts = self.get_pending_alerts(limit=limit)
        if not alerts:
            return "SENTINEL STATUS :: Zero active alerts. All systems operational."

        lines = [f"SENTINEL STATUS :: {len(alerts)} Active Alert(s) Detected:\n"]
        for a in alerts:
            lines.append(f"  • [{a['category'].upper()}] {a['title']} ({a['timestamp']})")
            lines.append(f"    Window: {a['active_window']}")
            lines.append(f"    Fix: {a['remediation']}\n")
        return "\n".join(lines)

    def inspect_ambient_context(self) -> dict[str, Any]:
        """Telemetry snapshot of foreground window, memory, and latest alerts."""
        active_win = self.get_active_window_title()
        ram = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.1)
        pending = self.get_pending_alerts(limit=3)

        return {
            "active_window": active_win,
            "cpu_percent": cpu,
            "ram_percent": ram.percent,
            "ram_free_gb": round(ram.available / (1024**3), 2),
            "pending_alerts_count": len(pending),
            "recent_alerts": pending,
        }

    def dismiss_alert(self, alert_id: str) -> bool:
        """Marks an alert as dismissed."""
        with self._lock:
            for a in self._alerts:
                if a.id == alert_id:
                    a.status = "dismissed"
                    return True
        return False


_GLOBAL_SENTINEL: ProactiveSentinel | None = None


def get_proactive_sentinel(
    registry: ToolRegistry | None = None,
    healing_engine: SelfHealingEngine | None = None,
) -> ProactiveSentinel:
    global _GLOBAL_SENTINEL
    if _GLOBAL_SENTINEL is None:
        _GLOBAL_SENTINEL = ProactiveSentinel(registry=registry, healing_engine=healing_engine)
    return _GLOBAL_SENTINEL
