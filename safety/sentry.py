"""Ambie-Sentry — Zero-Prompt Ambient Proactive Guardian for LUMI (Phase 7).

Continuously monitors system vitals, hardware, downloads, and git status:
  - Battery & Power: warns on low battery (<20% unplugged), notifies when fully charged.
  - Resources: warns on high memory (>90%) with top offending process name.
  - Downloads: detects newly completed downloads in real-time.
  - Night Git Check: checks for uncommitted work between 22:00 and 02:00.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from tools.cleanup import format_bytes


class AmbieSentry:
    """Proactive background sentry loop running zero-prompt contextual checks."""

    def __init__(
        self,
        config: dict | None = None,
        notifier: Any = None,
        db_path: str = "",
        downloads_path: str = "",
        workspace_path: str = ".",
    ) -> None:
        self.config = (config or {}).get("sentry") or {}
        self.notifier = notifier
        self.db_path = str(db_path)
        self.downloads_path = (Path(downloads_path) if downloads_path
                               else Path.home() / "Downloads")
        self.workspace_path = Path(workspace_path)

        self.enabled = bool(self.config.get("enabled", True))
        self.interval_s = max(5, int(self.config.get("interval_s", 25)))
        self.battery_threshold = int(self.config.get("battery_alert_pct", 20))
        self.ram_threshold = int(self.config.get("ram_alert_pct", 90))
        self.watch_downloads = bool(self.config.get("watch_downloads", True))
        self.git_night_reminder = bool(self.config.get("git_night_reminder", True))

        # Internal trackers
        self._last_battery_alert = 0.0
        self._last_battery_full_alert = False
        self._last_ram_alert = 0.0
        self._last_git_reminder_date = ""
        self._recent_events: list[dict] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        # Pre-seed existing downloads so we only alert on newly finished downloads
        self._seen_downloads: set[str] = set()
        self._init_downloads_cache()

    def _init_downloads_cache(self) -> None:
        if self.downloads_path.exists():
            try:
                for item in self.downloads_path.iterdir():
                    if item.is_file():
                        self._seen_downloads.add(item.name)
            except Exception:
                pass

    def check_battery(self) -> tuple[str, str, str] | None:
        """Check battery percent and power state."""
        try:
            import psutil

            batt = psutil.sensors_battery()
            if not batt:
                return None

            now = time.time()
            pct = round(batt.percent)
            plugged = batt.power_plugged

            # 1. Low battery (<20% and unplugged)
            if not plugged and pct <= self.battery_threshold:
                if now - self._last_battery_alert > 900:  # 15m cooldown
                    self._last_battery_alert = now
                    self._last_battery_full_alert = False
                    return (
                        "WARN",
                        "battery_low",
                        f"⚠ Boss, laptop battery {pct}% bachi hai aur charger unplugged hai. Kripya charger plug in kar lijiye!",
                    )

            # 2. Fully charged (100% and plugged)
            if plugged and pct >= 100:
                if not self._last_battery_full_alert:
                    self._last_battery_full_alert = True
                    return (
                        "INFO",
                        "battery_full",
                        "⚡ Laptop 100% full charge ho chuka hai. Chahein toh charger unplug kar sakte hain.",
                    )
            elif pct < 95:
                self._last_battery_full_alert = False

        except Exception:
            pass
        return None

    def check_resources(self) -> tuple[str, str, str] | None:
        """Check RAM consumption and pinpoint top process."""
        try:
            import psutil

            mem = psutil.virtual_memory()
            now = time.time()
            if mem.percent >= self.ram_threshold:
                if now - self._last_ram_alert > 3600:  # 60m cooldown (prevents console spam)
                    self._last_ram_alert = now
                    # Find top RAM consumer
                    top_name, top_mb = "System", 0.0
                    for p in psutil.process_iter(["name", "memory_info"]):
                        try:
                            rss = p.info["memory_info"].rss / (1024 * 1024)
                            if rss > top_mb:
                                top_name = p.info["name"]
                                top_mb = rss
                        except Exception:
                            continue

                    return (
                        "WARN",
                        "ram_spike",
                        f"⚡ RAM load {mem.percent}% par pahunch gaya hai. Top consumer: {top_name} ({round(top_mb, 1)} MB).",
                    )
        except Exception:
            pass
        return None

    def check_downloads(self) -> list[tuple[str, str, str]]:
        """Detect newly finished downloads in downloads directory."""
        events: list[tuple[str, str, str]] = []
        if not self.watch_downloads or not self.downloads_path.exists():
            return events

        try:
            current_files = set()
            for item in self.downloads_path.iterdir():
                if not item.is_file():
                    continue
                name = item.name
                current_files.add(name)

                # Ignore temp / in-progress download extensions
                if (
                    name.endswith(".crdownload")
                    or name.endswith(".tmp")
                    or name.endswith(".part")
                    or name.startswith("~$")
                ):
                    continue

                if name not in self._seen_downloads:
                    self._seen_downloads.add(name)
                    try:
                        sz = format_bytes(item.stat().st_size)
                    except Exception:
                        sz = "file"
                    events.append(
                        (
                            "INFO",
                            "new_download",
                            f"📥 Naya download detect hua: '{name}' ({sz}). Kya ise open ya inspect karna hai?",
                        )
                    )
            # Update seen cache
            self._seen_downloads = current_files
        except Exception:
            pass
        return events

    def check_git_uncommitted(self) -> tuple[str, str, str] | None:
        """Night work saver: checks for uncommitted changes between 22:00 and 02:00."""
        if not self.git_night_reminder:
            return None

        now = datetime.now()
        hour = now.hour
        today_str = now.strftime("%Y-%m-%d")

        # Active between 22:00 and 02:00
        if (hour >= 22 or hour < 2) and self._last_git_reminder_date != today_str:
            try:
                proc = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=str(self.workspace_path),
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                lines = [l for l in proc.stdout.splitlines() if l.strip()]
                if lines:
                    self._last_git_reminder_date = today_str
                    return (
                        "INFO",
                        "git_uncommitted",
                        f"🌙 Boss, aaj ka work uncommitted hai ({len(lines)} files modified). Kya ek safe commit create kar du?",
                    )
            except Exception:
                pass
        return None

    def poll_once(self) -> list[dict]:
        """Perform one comprehensive sentry poll cycle."""
        triggered: list[dict] = []
        checks = []

        # 1. Battery
        b_res = self.check_battery()
        if b_res:
            checks.append(b_res)

        # 2. RAM / CPU
        r_res = self.check_resources()
        if r_res:
            checks.append(r_res)

        # 3. Downloads
        d_res = self.check_downloads()
        checks.extend(d_res)

        # 4. Git Night check
        g_res = self.check_git_uncommitted()
        if g_res:
            checks.append(g_res)

        for sev, rule, msg in checks:
            ev = {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "severity": sev,
                "rule": rule,
                "message": msg,
            }
            triggered.append(ev)
            self._recent_events.append(ev)
            if len(self._recent_events) > 50:
                self._recent_events.pop(0)

            # Emit via notifier (to alerts table + telegram)
            if self.notifier:
                try:
                    self.notifier.emit(sev, rule, msg)
                except Exception:
                    pass

        return triggered

    def poll_loop(self) -> None:
        """Background thread loop."""
        while not self._stop.is_set():
            if self.enabled:
                try:
                    self.poll_once()
                except Exception as exc:
                    print(f"[sentry] poll error: {exc}")
            self._stop.wait(self.interval_s)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self.poll_loop, daemon=True, name="lumi-ambie-sentry")
        self._thread.start()
        print(f"[sentry] Ambie-Sentry guardian active (poll interval={self.interval_s}s)")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def get_status(self) -> dict:
        """Return real-time diagnostic payload."""
        batt_str = "Unavailable"
        plugged_str = "-"
        try:
            import psutil

            batt = psutil.sensors_battery()
            if batt:
                batt_str = f"{round(batt.percent)}%"
                plugged_str = "Plugged in ⚡" if batt.power_plugged else "On battery 🔋"
        except Exception:
            pass

        ram_pct = 0.0
        try:
            import psutil

            ram_pct = psutil.virtual_memory().percent
        except Exception:
            pass

        active_win = ""
        try:
            from brain.ollama_adapter import get_active_window_title
            active_win = get_active_window_title()
        except Exception:
            pass

        return {
            "enabled": self.enabled,
            "interval_s": self.interval_s,
            "battery": batt_str,
            "power": plugged_str,
            "ram_pct": ram_pct,
            "active_window": active_win or "Desktop",
            "monitored_downloads": str(self.downloads_path),
            "tracked_downloads_count": len(self._seen_downloads),
            "recent_events": self._recent_events[-5:],
        }


def sentry_status_text(sentry: AmbieSentry | None) -> str:
    """Format human-readable sentry status for user and LLM."""
    if not sentry:
        return "Ambie-Sentry guardian is not initialized."

    stat = sentry.get_status()
    lines = [
        "🛡️ **Ambie-Sentry Proactive Guardian Status:**",
        f"- Status: {'🟢 ACTIVE' if stat['enabled'] else '⚪ PAUSED'}",
        f"- Active Screen Window: `{stat.get('active_window', 'Desktop')}`",
        f"- Battery: {stat['battery']} ({stat['power']})",
        f"- RAM Load: {stat['ram_pct']}%",
        f"- Downloads Sentry: {stat['tracked_downloads_count']} files tracked in Downloads",
        f"- Poll Interval: {stat['interval_s']}s",
    ]

    events = stat.get("recent_events") or []
    if events:
        lines.append("\n**Recent Guardian Events:**")
        for ev in reversed(events):
            lines.append(f"- [{ev['ts']}] {ev['severity']} ({ev['rule']}): {ev['message']}")
    else:
        lines.append("- Recent Events: Clean ✅ (koi anomaly nahi)")

    return "\n".join(lines)
