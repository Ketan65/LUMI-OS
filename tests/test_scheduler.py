"""Tests for Phase 5: Proactive LUMI (Scheduler, Morning Briefing, Quiet Hours, Reminders)."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.orchestrator import Orchestrator
from core.scheduler import LumiScheduler, register_scheduler_tools
from memory.repo import MemoryRepo
from tools.registry import ToolRegistry


import gc

@pytest.fixture
def temp_memory():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = Path(tmp_dir) / "test_lumi.db"
        cfg = {"memory": {"db_path": str(db_path), "backup_dir": tmp_dir}}
        repo = MemoryRepo(cfg)
        yield repo
        del repo
        gc.collect()


def test_is_quiet_hours():
    sched = LumiScheduler()
    # 03:30 AM should be quiet hours (02:00 -> 05:30)
    quiet_time = datetime(2026, 10, 10, 3, 30)
    assert sched.is_quiet_hours(quiet_time) is True

    # 10:00 AM should NOT be quiet hours
    day_time = datetime(2026, 10, 10, 10, 0)
    assert sched.is_quiet_hours(day_time) is False


def test_generate_briefing():
    sched = LumiScheduler()
    briefing = sched.generate_briefing()
    assert "LUMI Morning Briefing" in briefing
    assert "System Health" in briefing
    assert "Chalo, aaj ka din" in briefing


def test_parse_time_input():
    sched = LumiScheduler()
    now = datetime.now()

    dt_delay = sched.parse_time_input(delay_minutes=30)
    assert 29 <= (dt_delay - now).total_seconds() / 60 <= 31

    dt_rel = sched.parse_time_input(time_str="+45m")
    assert 44 <= (dt_rel - now).total_seconds() / 60 <= 46

    dt_hours = sched.parse_time_input(time_str="+2h")
    assert 119 <= (dt_hours - now).total_seconds() / 60 <= 121


def test_reminder_tools_and_persistence(temp_memory):
    registry = ToolRegistry()
    notifier = MagicMock()
    sched = LumiScheduler(memory=temp_memory, notifier=notifier)
    register_scheduler_tools(registry, sched)

    set_tool = registry.get("set_reminder")
    list_tool = registry.get("list_reminders")
    cancel_tool = registry.get("cancel_reminder")

    assert set_tool is not None
    assert set_tool.risk == "auto"

    # 1. Set reminder
    res_set = set_tool.handler(text="Doctor appointment", delay_minutes=20)
    assert "Doctor appointment" in res_set
    assert "ID:" in res_set

    # 2. List reminders
    res_list = list_tool.handler()
    assert "Doctor appointment" in res_list

    # 3. Cancel reminder
    sid = res_set.split("ID:")[-1].strip()
    res_cancel = cancel_tool.handler(reminder_id=sid)
    assert "cancel ho gaya" in res_cancel

    # 4. List again (empty)
    res_empty = list_tool.handler()
    assert "Koi pending reminders nahi hain" in res_empty


def test_missed_reminder_recovery(temp_memory):
    past_iso = (datetime.now() - timedelta(minutes=10)).isoformat(timespec="seconds")
    sid = temp_memory.save_reminder("Drink water", past_iso)

    notifier = MagicMock()
    sched = LumiScheduler(memory=temp_memory, notifier=notifier)
    sched.recover_missed_reminders()

    # Check notification was fired with missed note
    notifier.emit.assert_called_once()
    args = notifier.emit.call_args[0]
    assert "Drink water (missed while offline)" in args[2]

    # Status in DB should now be completed
    pending = temp_memory.list_reminders(status="pending")
    assert len(pending) == 0


def test_orchestrator_briefing_and_reminders_commands(temp_memory):
    registry = ToolRegistry()
    sched = LumiScheduler(memory=temp_memory)
    register_scheduler_tools(registry, sched)

    orc = Orchestrator(brain=MagicMock(), memory=temp_memory, registry=registry)
    _, briefing_text = orc.command("/briefing")
    assert "LUMI Morning Briefing" in briefing_text

    _, rem_text = orc.command("/reminders")
    assert "Koi pending reminders nahi hain" in rem_text
