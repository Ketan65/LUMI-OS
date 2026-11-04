"""Tests for Phase 5 GUI automation tools."""

from unittest.mock import MagicMock, patch

from tools.gui import gui_control, register_gui_tools
from tools.registry import ToolRegistry


def test_gui_control_validation():
    res = gui_control("")
    assert "Error: action required" in res

    res2 = gui_control("unknown_action_xyz")
    assert "Unknown gui_control action" in res2


def test_gui_control_media():
    with patch("tools.gui._send_vk") as mock_vk:
        res = gui_control("media", text="next")
        assert "Sent media NEXT track command" in res
        mock_vk.assert_called_once()


def test_gui_control_hotkey():
    with patch("pyautogui.hotkey") as mock_hotkey:
        res = gui_control("hotkey", keys=["ctrl", "shift", "esc"])
        assert "Executed hotkey: ctrl + shift + esc" in res
        mock_hotkey.assert_called_once_with("ctrl", "shift", "esc")


def test_gui_control_type_text():
    with patch("pyautogui.write") as mock_write:
        res = gui_control("type_text", text="Hello from LUMI")
        assert "Typed 15 characters" in res
        mock_write.assert_called_once_with("Hello from LUMI", interval=0.02)


def test_gui_control_press_key():
    with patch("pyautogui.press") as mock_press:
        res = gui_control("press_key", text="enter")
        assert "Pressed key 'enter'" in res
        mock_press.assert_called_once_with("enter")


def test_gui_control_get_mouse():
    mock_pos = MagicMock()
    mock_pos.x = 500
    mock_pos.y = 300
    with patch("pyautogui.position", return_value=mock_pos):
        res = gui_control("get_mouse")
        assert "Current mouse position: x=500, y=300" in res


def test_register_gui_tools():
    reg = ToolRegistry()
    register_gui_tools(reg)
    tool = reg.get("gui_control")
    assert tool is not None
    assert tool.risk == "auto"
    assert "action" in tool.params_schema["properties"]
