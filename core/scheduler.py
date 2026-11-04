"""Proactive LUMI scheduler — in-process APScheduler + persistent reminders + morning briefing.

Features:
  - Quiet hours enforcement: respects values.yaml hard_rules (02:00 -> wake_time suppress/defer).
  - Daily morning briefing at wake_time (default 05:30): goals, rules, storage, and alerts.
  - Persistent reminders: survives LUMI restarts via SQLite schedules table in lumi.db.
  - Missed-run recovery: automatically handles reminders that expired while PC was off.
  - LLM tools: set_reminder, list_reminders, cancel_reminder (risk: auto).
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from core import values as V
from memory.repo import MemoryRepo
from tools.cleanup import format_bytes
from tools.registry import Tool, ToolRegistry


class LumiScheduler:
    """Manages scheduled jobs, morning briefings, quiet hours, and reminders."""

    def __init__(self, memory: MemoryRepo | None = None, notifier=None, config: dict | None = None) -> None:
        self.memory = memory
        self.notifier = notifier
        self.config = config or {}
        self.scheduler = BackgroundScheduler()
        self._started = False

    def is_quiet_hours(self, now: datetime | None = None) -> bool:
        """Evaluates whether current time is within quiet hours (e.g. 02:00 to wake_time)."""
        dt = now or datetime.now()
        val = V.load_values()
        health = val.get("health") or {}
        wake_str = str(health.get("wake_time", "05:30")).strip()

        try:
            wake_h, wake_m = (int(x) for x in wake_str.split(":", 1))
        except (ValueError, AttributeError):
            wake_h, wake_m = 5, 30

        curr_minutes = dt.hour * 60 + dt.minute
        quiet_start = 2 * 60        # 02:00 (Raat 2 baje hard rule)
        quiet_end = wake_h * 60 + wake_m

        if quiet_start <= curr_minutes < quiet_end:
            return True
        return False

    def generate_briefing(self) -> str:
        """Constructs a concise, structured morning briefing in Hinglish."""
        now = datetime.now()
        date_str = now.strftime("%d %b %Y, %A")
        val = V.load_values()

        lines: list[str] = [
            f"🌅 **Shubh Prabhaat boss! LUMI Morning Briefing**",
            f"📅 {date_str}\n",
        ]

        # 1. Goals & Deadlines
        goals = val.get("goals") or []
        if goals:
            lines.append("🎯 **Active Goals & Deadlines:**")
            for g in goals:
                if isinstance(g, dict):
                    nm = g.get("name", "Goal")
                    dl = g.get("deadline", "")
                    lines.append(f"- {nm}" + (f" (deadline: {dl})" if dl else ""))
                else:
                    lines.append(f"- {g}")
            lines.append("")

        # 2. Today's Rules & Guidelines
        time_rules = (val.get("time") or {}).get("rules") or []
        health_rules = (val.get("health") or {}).get("rules") or []
        if time_rules or health_rules:
            lines.append("💡 **Today's Focus & Rules:**")
            for r in time_rules:
                lines.append(f"- [Time] {r}")
            for r in health_rules:
                lines.append(f"- [Health] {r}")
            lines.append("")

        # 3. System Health & Storage
        lines.append("📊 **System Health:**")
        try:
            home_dir = Path(".").resolve()
            usage = shutil.disk_usage(str(home_dir))
            free_str = format_bytes(usage.free)
            lines.append(f"- Disk Free: {free_str}")
        except Exception:
            lines.append("- Disk: status normal")

        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.1)
            ram = psutil.virtual_memory().percent
            lines.append(f"- Hardware: CPU {cpu}%, RAM {ram}%")
            batt = psutil.sensors_battery()
            if batt:
                plug = "Plugged in ⚡" if batt.power_plugged else "On battery 🔋"
                lines.append(f"- Battery: {round(batt.percent)}% ({plug})")
        except Exception:
            pass

        # 4. Pending Reminders & Agenda
        if self.memory:
            try:
                rems = self.memory.list_reminders("pending")
                if rems:
                    lines.append("\n⏰ **Pending Reminders & Agenda:**")
                    for r in rems[:5]:
                        lines.append(f"- [{r.get('trigger_time', 'Pending')}] {r.get('payload', '')}")
            except Exception:
                pass

        # 5. Recent Watchdog Alerts
        if self.memory:
            try:
                from safety.notifier import recent_alerts
                alerts = recent_alerts(str(self.memory.db_path), limit=3)
                if alerts:
                    lines.append(f"\n⚡ Recent Alerts: {len(alerts)} items recorded")
                else:
                    lines.append("\n⚡ Alerts: Clean ✅ (koi critical issue nahi)")
            except Exception:
                lines.append("\n⚡ Alerts: Normal")

        lines.append("\nChalo, aaj ka din shuru karte hain! Bolo boss, kya karna hai?")
        return "\n".join(lines)

    def _briefing_job(self) -> None:
        """Triggered automatically at wake time."""
        if self.is_quiet_hours():
            return
        briefing = self.generate_briefing()
        if self.notifier:
            try:
                self.notifier.emit("INFO", "morning_briefing", briefing)
            except Exception:
                pass
        print(f"\n[LUMI Morning Briefing]\n{briefing}\n")

    def _reminder_fired(self, sid: str, text: str) -> None:
        """Triggered when a reminder time is reached."""
        if self.memory:
            self.memory.complete_reminder(sid)
        msg = f"⏰ Reminder: {text}"
        if self.notifier:
            try:
                self.notifier.emit("INFO", "reminder", msg)
            except Exception:
                pass
        print(f"\n🔔 [REMINDER] {text}\n")

    def schedule_reminder(self, text: str, run_at: datetime) -> str:
        """Saves reminder and registers with scheduler."""
        run_iso = run_at.isoformat(timespec="seconds")
        sid = self.memory.save_reminder(text, run_iso) if self.memory else f"rem_{int(run_at.timestamp())}"

        self.scheduler.add_job(
            self._reminder_fired,
            trigger=DateTrigger(run_date=run_at),
            args=[sid, text],
            id=sid,
            replace_existing=True,
        )
        return sid

    def parse_time_input(self, delay_minutes: int | None = None,
                         time_str: str | None = None) -> datetime:
        """Parses natural time inputs (+Xm, HH:MM, YYYY-MM-DD HH:MM)."""
        now = datetime.now()
        if delay_minutes and delay_minutes > 0:
            return now + timedelta(minutes=int(delay_minutes))

        raw = (time_str or "").strip().lower()
        if not raw:
            return now + timedelta(minutes=10)  # Default 10 min

        # Pattern: "+15m" or "+2h"
        m_rel = re.match(r"^\+?(\d+)\s*(m|min|minute|minutes|h|hr|hour|hours)$", raw)
        if m_rel:
            qty, unit = int(m_rel.group(1)), m_rel.group(2)
            if unit.startswith("h"):
                return now + timedelta(hours=qty)
            return now + timedelta(minutes=qty)

        # Pattern: "HH:MM" (e.g. "16:30")
        m_time = re.match(r"^(\d{1,2}):(\d{2})$", raw)
        if m_time:
            h, m = int(m_time.group(1)), int(m_time.group(2))
            cand = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if cand <= now:
                cand += timedelta(days=1)  # Next day if time already passed today
            return cand

        # Pattern: "YYYY-MM-DD HH:MM"
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M"):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                pass

        # Fallback
        return now + timedelta(minutes=15)

    def recover_missed_reminders(self) -> None:
        """Recovers reminders stored in SQLite when LUMI restarts."""
        if not self.memory:
            return
        pending = self.memory.list_reminders(status="pending")
        now = datetime.now()

        for r in pending:
            sid = r["id"]
            text = r["payload"]
            try:
                target_dt = datetime.fromisoformat(r["trigger_time"])
            except ValueError:
                continue

            if target_dt <= now:
                # Missed while offline -> fire immediately and mark complete
                self._reminder_fired(sid, f"{text} (missed while offline)")
            else:
                # Still in future -> schedule job
                self.scheduler.add_job(
                    self._reminder_fired,
                    trigger=DateTrigger(run_date=target_dt),
                    args=[sid, text],
                    id=sid,
                    replace_existing=True,
                )

    def start(self) -> None:
        if self._started:
            return

        val = V.load_values()
        wake_str = str((val.get("health") or {}).get("wake_time", "05:30")).strip()
        try:
            wake_h, wake_m = (int(x) for x in wake_str.split(":", 1))
        except (ValueError, AttributeError):
            wake_h, wake_m = 5, 30

        # Daily Morning Briefing Cron
        self.scheduler.add_job(
            self._briefing_job,
            trigger=CronTrigger(hour=wake_h, minute=wake_m),
            id="lumi_morning_briefing",
            replace_existing=True,
        )

        self.recover_missed_reminders()
        self.scheduler.start()
        self._started = True

    def stop(self) -> None:
        if self._started:
            self.scheduler.shutdown(wait=False)
            self._started = False


# ── LLM Tools ─────────────────────────────────────────────────────────────────

def register_scheduler_tools(registry: ToolRegistry, scheduler: LumiScheduler) -> None:
    def set_reminder_handler(text: str, delay_minutes: int | None = None,
                             time_str: str | None = None) -> str:
        """Sets a timed reminder."""
        text_clean = (text or "").strip()
        if not text_clean:
            return "Reminder text cannot be empty."

        target_dt = scheduler.parse_time_input(delay_minutes, time_str)
        sid = scheduler.schedule_reminder(text_clean, target_dt)
        return (f"⏰ Reminder set: '{text_clean}'\n"
                f"Time: {target_dt.strftime('%d %b %Y, %H:%M')}\n"
                f"ID: {sid}")

    def list_reminders_handler() -> str:
        """Lists all pending reminders."""
        if not scheduler.memory:
            return "Memory not attached."
        items = scheduler.memory.list_reminders(status="pending")
        if not items:
            return "Koi pending reminders nahi hain."
        lines = ["⏰ **Pending Reminders:**"]
        for r in items:
            lines.append(f"- [{r['id']}] {r['trigger_time']} — {r['payload']}")
        return "\n".join(lines)

    def cancel_reminder_handler(reminder_id: str) -> str:
        """Cancels a pending reminder by ID."""
        rid = (reminder_id or "").strip()
        if not rid:
            return "Reminder ID cannot be empty."
        if scheduler.memory and scheduler.memory.cancel_reminder(rid):
            try:
                scheduler.scheduler.remove_job(rid)
            except Exception:
                pass
            return f"Reminder {rid} cancel ho gaya."
        return f"Reminder {rid} nahi mila."

    registry.register(Tool(
        name="set_reminder",
        description="Sets a reminder for a specific time or delay (e.g. '+30m', '17:00', or delay_minutes=15).",
        params_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "What to remind you about."},
                "delay_minutes": {"type": "integer", "description": "Minutes from now (e.g. 15, 30)."},
                "time_str": {"type": "string", "description": "Time string e.g. '16:00', '+45m', '2026-10-12 10:00'."},
            },
            "required": ["text"],
        },
        handler=set_reminder_handler,
        risk="auto",
    ))

    registry.register(Tool(
        name="list_reminders",
        description="Lists all pending scheduled reminders.",
        params_schema={"type": "object", "properties": {}},
        handler=list_reminders_handler,
        risk="auto",
    ))

    registry.register(Tool(
        name="cancel_reminder",
        description="Cancels an active reminder by ID.",
        params_schema={
            "type": "object",
            "properties": {
                "reminder_id": {"type": "string", "description": "The ID of the reminder to cancel."},
            },
            "required": ["reminder_id"],
        },
        handler=cancel_reminder_handler,
        risk="auto",
    ))


_GLOBAL_SCHEDULER: LumiScheduler | None = None


def get_lumi_scheduler(memory: MemoryRepo | None = None, notifier=None, config=None) -> LumiScheduler:
    global _GLOBAL_SCHEDULER
    if _GLOBAL_SCHEDULER is None:
        _GLOBAL_SCHEDULER = LumiScheduler(memory=memory, notifier=notifier, config=config)
    return _GLOBAL_SCHEDULER
