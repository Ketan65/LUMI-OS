"""Unit tests for Phase 12 NEXUS-IOT (Smart Workstation, LAN & Hardware IoT Control)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import httpx
import pytest

from core.nexus import NexusHub, get_local_ip
from tools.nexus import register_nexus_tools
from tools.registry import ToolRegistry
from web.server import create_app


def test_get_local_ip():
    ip = get_local_ip()
    assert isinstance(ip, str)
    assert len(ip.split(".")) == 4


def test_nexus_focus_presets():
    hub = NexusHub()
    # Initial state
    assert hub.current_preset == "reset"

    # Set valid preset
    res = hub.set_focus_preset("code_sprint")
    assert res["ok"] is True
    assert res["preset"] == "code_sprint"
    assert res["dnd"] is True
    assert hub.current_preset == "code_sprint"

    # Set presentation mode
    res2 = hub.set_focus_preset("presentation")
    assert res2["ok"] is True
    assert res2["audio_level"] == 0

    # Invalid preset
    res_err = hub.set_focus_preset("turbo_boost_9000")
    assert res_err["ok"] is False
    assert "Unknown preset" in res_err["error"]


def test_nexus_scan_lan():
    hub = NexusHub()
    devices = hub.scan_lan(subnet_prefix="127.0.0", max_hosts=2)
    assert len(devices) >= 1
    local_dev = devices[0]
    assert local_dev.is_alive is True
    assert local_dev.ip is not None


class MockWebHookResponse:
    def __init__(self, content: bytes, status: int = 200):
        self._content = content
        self.status = status

    def read(self):
        return self._content

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


@patch("urllib.request.urlopen")
def test_nexus_trigger_webhook(mock_urlopen):
    mock_urlopen.return_value = MockWebHookResponse(b'{"status": "scene_activated"}')

    hub = NexusHub()
    res = hub.trigger_webhook("http://192.168.1.50/api/webhook", {"scene": "night"})
    assert res["ok"] is True
    assert res["status_code"] == 200
    assert "scene_activated" in res["response"]


@patch("urllib.request.urlopen")
def test_nexus_trigger_webhook_error(mock_urlopen):
    mock_urlopen.side_effect = RuntimeError("Host unreachable")

    hub = NexusHub()
    res = hub.trigger_webhook("http://192.168.1.99:8123/webhook")
    assert res["ok"] is False
    assert res["status_code"] == 500
    assert "Host unreachable" in res["error"]


def test_nexus_tools_and_commands():
    from core.orchestrator import Orchestrator

    reg = ToolRegistry()
    hub = NexusHub()
    register_nexus_tools(reg, hub=hub)

    assert reg.get("workstation_focus") is not None
    assert reg.get("scan_lan_devices") is not None
    assert reg.get("iot_webhook") is not None

    # Tool handler: focus
    out = reg.get("workstation_focus").handler(preset="chill")
    assert "CHILL" in out

    # Tool handler: scan
    out_scan = reg.get("scan_lan_devices").handler()
    assert "NEXUS Local Network Discovery" in out_scan

    # Orchestrator commands
    mock_orc = Orchestrator(brain=MagicMock())
    mock_orc.registry = reg
    mock_orc.nexus = hub

    _, msg_st = mock_orc.command("/nexus status")
    assert "NEXUS-IOT:" in msg_st

    _, msg_fc = mock_orc.command("/nexus focus presentation")
    assert "PRESENTATION" in msg_fc


def test_nexus_web_routes():
    mock_orc = MagicMock()
    mock_orc.config = {"web": {"auth_token": ""}}
    mock_orc.memory = None

    hub = NexusHub()
    mock_orc.nexus = hub

    app = create_app(mock_orc)
    transport = httpx.ASGITransport(app=app)

    async def run_checks():
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as client:
            # Status
            r1 = await client.get("/api/nexus/status")
            assert r1.status_code == 200
            assert "available_presets" in r1.json()

            # Focus
            r2 = await client.post("/api/nexus/focus", json={"preset": "code_sprint"})
            assert r2.status_code == 200
            assert r2.json()["ok"] is True

            # Scan
            r3 = await client.get("/api/nexus/scan")
            assert r3.status_code == 200
            assert len(r3.json()["devices"]) >= 1

            # Trigger validation
            r4 = await client.post("/api/nexus/trigger", json={"url": "  "})
            assert r4.status_code == 400

    asyncio.run(run_checks())
