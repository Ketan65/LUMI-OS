"""Tests for Windows OS desktop control tools."""

from tools.desktop import open_app, open_url, register_desktop_tools, system_control
from tools.registry import ToolRegistry


def test_open_app_validation():
    res = open_app("")
    assert "Error: app_name required" in res


def test_open_url_validation():
    res = open_url()
    assert "Error: provide either a 'url' or a 'search_query'" in res


def test_open_url_youtube_mapping(monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda u: opened.append(u))

    res = open_url(search_query="lofi chill beats", platform="youtube")
    assert "Successfully opened" in res
    assert len(opened) == 1
    assert "youtube.com/results" in opened[0]
    assert "lofi%20chill%20beats" in opened[0]


def test_system_control_battery():
    res = system_control("battery")
    assert isinstance(res, str)
    assert "Battery" in res or "not available" in res


def test_system_control_info():
    res = system_control("system_info")
    assert "System Specs" in res
    assert "CPU Load" in res
    assert "RAM" in res


def test_system_control_active_apps():
    res = system_control("active_apps")
    assert "Active applications" in res or "Could not list" in res


def test_system_control_unknown():
    res = system_control("invalid_action")
    assert "Unknown system_control action" in res


def test_register_desktop_tools():
    reg = ToolRegistry()
    register_desktop_tools(reg)
    names = [t.name for t in reg.list_all()]
    assert "open_app" in names
    assert "open_url" in names
    assert "system_control" in names
