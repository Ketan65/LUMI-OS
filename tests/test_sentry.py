"""Tests for Phase 7 AMBIE-SENTRY: Zero-Prompt Proactive Guardian."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from safety.sentry import AmbieSentry, sentry_status_text
from tools.registry import ToolRegistry
from tools.sentry import register_sentry_tools


def test_sentry_battery_low(tmp_path):
    sentry = AmbieSentry(
        config={"sentry": {"battery_alert_pct": 20}},
        downloads_path=str(tmp_path / "downloads"),
        workspace_path=str(tmp_path / "workspace"),
    )

    mock_batt = MagicMock(percent=18, power_plugged=False)
    with patch("psutil.sensors_battery", return_value=mock_batt):
        res = sentry.check_battery()
        assert res is not None
        sev, rule, msg = res
        assert sev == "WARN"
        assert rule == "battery_low"
        assert "18% bachi hai" in msg


def test_sentry_battery_full(tmp_path):
    sentry = AmbieSentry(
        config={"sentry": {"battery_alert_pct": 20}},
        downloads_path=str(tmp_path / "downloads"),
        workspace_path=str(tmp_path / "workspace"),
    )

    mock_batt = MagicMock(percent=100, power_plugged=True)
    with patch("psutil.sensors_battery", return_value=mock_batt):
        res = sentry.check_battery()
        assert res is not None
        sev, rule, msg = res
        assert sev == "INFO"
        assert rule == "battery_full"


def test_sentry_downloads_watcher(tmp_path):
    dl_dir = tmp_path / "downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)

    # Initial file (seeded on init, should not trigger alert)
    (dl_dir / "old_file.txt").write_text("old")

    sentry = AmbieSentry(
        config={"sentry": {"watch_downloads": True}},
        downloads_path=str(dl_dir),
        workspace_path=str(tmp_path / "workspace"),
    )

    # Polling initially -> no events
    events = sentry.check_downloads()
    assert len(events) == 0

    # New file added
    (dl_dir / "dataset.zip").write_text("data")
    # Temp in-progress download added (should be skipped)
    (dl_dir / "video.mp4.crdownload").write_text("temp")

    events2 = sentry.check_downloads()
    assert len(events2) == 1
    assert "dataset.zip" in events2[0][2]
    assert "video.mp4.crdownload" not in events2[0][2]


def test_sentry_status_and_tool(tmp_path):
    sentry = AmbieSentry(
        config={"sentry": {"enabled": True}},
        downloads_path=str(tmp_path / "downloads"),
        workspace_path=str(tmp_path / "workspace"),
    )

    text = sentry_status_text(sentry)
    assert "Ambie-Sentry Proactive Guardian" in text
    assert "ACTIVE" in text

    reg = ToolRegistry()
    register_sentry_tools(reg, sentry)
    tool = reg.get("sentry_status")
    assert tool is not None
    assert "Ambie-Sentry" in tool.handler()
