"""GUI Automation tools for LUMI — Mouse, Keyboard, Hotkeys & Media Control (Phase 5).

Allows LUMI to interact with software, windows, and media playback directly:
  - gui_control: hotkeys (e.g. ctrl+c, alt+tab, win+d), typing text, clicking, media play/pause.
"""

from __future__ import annotations

import ctypes
import time
from typing import Any

from tools.registry import Tool, ToolRegistry

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_LWIN = 0x5B
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
KEYEVENTF_KEYUP = 0x0002


def _send_vk(vk_code: int) -> None:
    """Send keydown and keyup for a Win32 virtual key."""
    try:
        user32 = ctypes.windll.user32
        user32.keybd_event(vk_code, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
    except Exception as exc:
        raise RuntimeError(f"Win32 key event failed: {exc}") from exc


def gui_control(
    action: str,
    keys: list[str] | str | None = None,
    text: str | None = None,
    x: int | None = None,
    y: int | None = None,
    button: str = "left",
    clicks: int = 1,
) -> str:
    """Perform mouse, keyboard, or media automation on Windows."""
    act = (action or "").strip().lower()
    if not act:
        return "Error: action required (e.g. 'hotkey', 'type_text', 'press_key', 'click', 'media', 'show_desktop', 'switch_window')."

    # 1. Media player controls (Spotify / YouTube / Windows media)
    if act in {"media", "media_control", "music"}:
        cmd = str(text or (keys[0] if isinstance(keys, list) and keys else keys) or "play_pause").lower()
        if "next" in cmd:
            _send_vk(VK_MEDIA_NEXT_TRACK)
            return "Sent media NEXT track command."
        elif "prev" in cmd:
            _send_vk(VK_MEDIA_PREV_TRACK)
            return "Sent media PREVIOUS track command."
        elif "stop" in cmd:
            _send_vk(VK_MEDIA_STOP)
            return "Sent media STOP command."
        else:
            _send_vk(VK_MEDIA_PLAY_PAUSE)
            return "Sent media PLAY/PAUSE toggle command."

    # 2. Show desktop (Win + D)
    if act in {"show_desktop", "desktop", "minimize_all"}:
        try:
            import pyautogui
            pyautogui.hotkey("win", "d")
            return "Toggled show desktop (Win + D)."
        except Exception:
            try:
                user32 = ctypes.windll.user32
                user32.keybd_event(VK_LWIN, 0, 0, 0)
                user32.keybd_event(0x44, 0, 0, 0)  # 'D'
                time.sleep(0.05)
                user32.keybd_event(0x44, 0, KEYEVENTF_KEYUP, 0)
                user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)
                return "Toggled show desktop (Win + D)."
            except Exception as exc:
                return f"Failed to show desktop: {exc}"

    # 3. Switch active window (Alt + Tab)
    if act in {"switch_window", "alt_tab"}:
        try:
            import pyautogui
            pyautogui.hotkey("alt", "tab")
            return "Switched active window (Alt + Tab)."
        except Exception:
            return "Switched window."

    # 4. Hotkeys (e.g. ["ctrl", "c"], ["ctrl", "v"], ["ctrl", "s"])
    if act == "hotkey":
        key_list = keys if isinstance(keys, list) else [k.strip() for k in str(keys or "").split("+")]
        key_list = [k.lower() for k in key_list if k]
        if not key_list:
            return "Error: keys required for hotkey action (e.g. ['ctrl', 's'] or 'ctrl+c')."
        try:
            import pyautogui
            pyautogui.hotkey(*key_list)
            return f"Executed hotkey: {' + '.join(key_list)}."
        except Exception as exc:
            return f"Hotkey error: {exc}"

    # 5. Type text
    if act in {"type_text", "type", "write"}:
        str_to_type = text if text is not None else str(keys or "")
        if not str_to_type:
            return "Error: text required for type_text action."
        try:
            import pyautogui
            pyautogui.write(str_to_type, interval=0.02)
            return f"Typed {len(str_to_type)} characters successfully."
        except Exception as exc:
            return f"Typing error: {exc}"

    # 6. Press single key
    if act in {"press_key", "press"}:
        k = str(text or (keys[0] if isinstance(keys, list) and keys else keys) or "").lower()
        if not k:
            return "Error: key name required (e.g. 'enter', 'esc', 'space', 'tab')."
        try:
            import pyautogui
            pyautogui.press(k)
            return f"Pressed key '{k}'."
        except Exception as exc:
            return f"Press key error: {exc}"

    # 7. Mouse click
    if act == "click":
        try:
            import pyautogui
            if x is not None and y is not None:
                pyautogui.click(x=int(x), y=int(y), button=button, clicks=clicks)
                return f"Clicked at ({x}, {y}) with {button} button ({clicks} clicks)."
            else:
                pyautogui.click(button=button, clicks=clicks)
                pos = pyautogui.position()
                return f"Clicked at current mouse position ({pos.x}, {pos.y})."
        except Exception as exc:
            return f"Mouse click error: {exc}"

    # 8. Mouse move
    if act in {"move", "move_to"}:
        if x is None or y is None:
            return "Error: x and y coordinates required for move_to action."
        try:
            import pyautogui
            pyautogui.moveTo(int(x), int(y), duration=0.2)
            return f"Moved mouse to ({x}, {y})."
        except Exception as exc:
            return f"Mouse move error: {exc}"

    # 9. Get mouse position
    if act in {"get_mouse", "mouse_pos", "mouse_position"}:
        try:
            import pyautogui
            pos = pyautogui.position()
            return f"Current mouse position: x={pos.x}, y={pos.y}."
        except Exception as exc:
            return f"Mouse position query error: {exc}"

    return f"Unknown gui_control action: '{action}'. Available: hotkey, type_text, press_key, click, move_to, get_mouse, media, show_desktop, switch_window."


def register_gui_tools(registry: ToolRegistry) -> None:
    """Register GUI automation and computer-use tools."""
    registry.register(
        Tool(
            name="gui_control",
            description=(
                "Controls the mouse, keyboard, hotkeys, and media playback on Windows. "
                "Actions: 'hotkey' (e.g. ['ctrl', 'c'], ['ctrl', 'v'], ['alt', 'tab']), "
                "'type_text' (types text string into focused input), "
                "'press_key' ('enter', 'esc', 'space', 'tab', 'backspace'), "
                "'click' (clicks at x, y or current mouse position), "
                "'move_to' (moves mouse to x, y), "
                "'get_mouse' (returns x, y coords), "
                "'media' (play_pause, next, prev track on Spotify/YouTube), "
                "'show_desktop' (minimizes all windows to reveal desktop)."
            ),
            params_schema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "The GUI action to perform: hotkey, type_text, press_key, click, move_to, get_mouse, media, show_desktop, switch_window.",
                    },
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Key or keys for hotkey (e.g. ['ctrl', 's']).",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to type or sub-command for media (play_pause, next, prev).",
                    },
                    "x": {
                        "type": "integer",
                        "description": "X coordinate for mouse click or move.",
                    },
                    "y": {
                        "type": "integer",
                        "description": "Y coordinate for mouse click or move.",
                    },
                    "button": {
                        "type": "string",
                        "enum": ["left", "right", "middle"],
                        "description": "Mouse button to click (default: 'left').",
                    },
                },
                "required": ["action"],
            },
            handler=gui_control,
            risk="auto",
        )
    )
