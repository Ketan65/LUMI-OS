"""Desktop & Windows OS control tools for LUMI — HANDS.

Enables LUMI to interact with and control the user's Windows PC:
  - open_app: launch apps (Notepad, VS Code, Chrome, Edge, Spotify, Calculator, Explorer, etc.)
  - open_url: open websites or search YouTube / Google in the default browser
  - system_control: control volume (up/down/mute), lock workstation, check battery & system info
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import urllib.parse
import webbrowser
from typing import Any

from tools.registry import Tool, ToolRegistry

APP_SHORTCUTS: dict[str, str] = {
    "notepad": "notepad.exe",
    "calc": "calc.exe",
    "calculator": "calc.exe",
    "code": "code",
    "vscode": "code",
    "vs code": "code",
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "google chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "msedge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "browser": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "explorer": "explorer.exe",
    "files": "explorer.exe",
    "file manager": "explorer.exe",
    "cmd": "cmd.exe",
    "terminal": "powershell.exe",
    "powershell": "powershell.exe",
    "taskmgr": "taskmgr.exe",
    "task manager": "taskmgr.exe",
    "spotify": "spotify:",
    "settings": "ms-settings:",
}


def open_app(app_name: str, args: str = "") -> str:
    """Launch or focus a Windows desktop application."""
    app_clean = (app_name or "").strip().lower()
    if not app_clean:
        return "Error: app_name required (e.g. 'notepad', 'code', 'chrome', 'calc')."

    target = APP_SHORTCUTS.get(app_clean, app_name.strip())

    try:
        # 1. URI protocol (spotify:, ms-settings:)
        if isinstance(target, str) and (target.endswith(":") or target.startswith("ms-")):
            os.startfile(target)
            return f"Successfully opened {app_name}."

        # 2. Known executable path
        if isinstance(target, str) and os.path.isabs(target) and os.path.exists(target):
            cmd = [target]
            if args:
                cmd.extend(args.split())
            subprocess.Popen(cmd)
            return f"Successfully launched {app_name}."

        # 3. System PATH lookup
        resolved = shutil.which(target if isinstance(target, str) else app_name)
        if resolved:
            cmd = [resolved]
            if args:
                cmd.extend(args.split())
            subprocess.Popen(cmd)
            return f"Successfully launched {app_name}."

        # 4. Fallback os.startfile or shell start
        try:
            os.startfile(target if isinstance(target, str) else app_name)
            return f"Successfully launched {app_name}."
        except Exception:
            subprocess.Popen(f"start {target}", shell=True)
            return f"Sent system start command for {app_name}."

    except Exception as exc:
        return f"Could not launch '{app_name}': {exc}"


def open_url(url: str = "", search_query: str = "", platform: str = "web") -> str:
    """Opens a website URL or searches YouTube / Google in the default browser."""
    target_url = (url or "").strip()
    query = (search_query or "").strip()
    plat = (platform or "web").lower().strip()

    if not target_url and not query:
        return "Error: provide either a 'url' or a 'search_query'."

    # If search_query provided without url:
    if query and not target_url:
        if plat == "youtube" or "youtube" in query.lower() or "gaana" in query.lower() or "song" in query.lower() or "video" in query.lower():
            clean_q = query.replace("youtube", "").replace("YouTube", "").strip()
            target_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(clean_q or query)}"
        else:
            target_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"

    # Ensure http/https
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    try:
        webbrowser.open(target_url)
        return f"Successfully opened: {target_url}"
    except Exception as exc:
        return f"Failed to open URL '{target_url}': {exc}"


def system_control(action: str, value: str = "") -> str:
    """Controls Windows OS volume, workstation lock, battery, and system info."""
    act = (action or "").lower().strip()

    # 1. Volume Up / Down / Mute
    user32 = getattr(ctypes.windll, "user32", None)
    if act in ("volume_up", "vol_up"):
        if user32:
            for _ in range(5):
                user32.keybd_event(0xAF, 0, 0, 0)
                user32.keybd_event(0xAF, 0, 2, 0)
            return "Master volume increased by ~10%."
        return "user32 unavailable."

    if act in ("volume_down", "vol_down"):
        if user32:
            for _ in range(5):
                user32.keybd_event(0xAE, 0, 0, 0)
                user32.keybd_event(0xAE, 0, 2, 0)
            return "Master volume decreased by ~10%."
        return "user32 unavailable."

    if act in ("mute", "unmute", "toggle_mute"):
        if user32:
            user32.keybd_event(0xAD, 0, 0, 0)
            user32.keybd_event(0xAD, 0, 2, 0)
            return "Toggled audio mute state."
        return "user32 unavailable."

    # 2. Lock Workstation
    if act in ("lock", "lock_pc", "lock_workstation"):
        if user32 and hasattr(user32, "LockWorkStation"):
            user32.LockWorkStation()
            return "Windows PC workstation locked."
        return "LockWorkStation function unavailable."

    # 3. Battery Info
    if act in ("battery", "power"):
        try:
            import psutil
            bat = psutil.sensors_battery()
            if not bat:
                return "Battery sensor not available (Desktop PC or virtual machine)."
            plugged = "Plugged in (Charging)" if bat.power_plugged else "Running on Battery"
            pct = bat.percent
            mins_left = f"{int(bat.secsleft / 60)} mins remaining" if bat.secsleft > 0 else "Full / Calculating"
            return f"Battery: {pct}% | Status: {plugged} | Time: {mins_left}"
        except Exception as exc:
            return f"Could not read battery status: {exc}"

    # 4. System Info (CPU / RAM / OS)
    if act in ("system_info", "status", "specs"):
        try:
            import platform
            import psutil
            cpu = psutil.cpu_percent(interval=0.1)
            vm = psutil.virtual_memory()
            ram_used_gb = round((vm.total - vm.available) / (1024**3), 1)
            ram_total_gb = round(vm.total / (1024**3), 1)
            os_name = f"{platform.system()} {platform.release()} ({platform.architecture()[0]})"
            return (f"System Specs: {os_name} | CPU Load: {cpu}% | "
                    f"RAM: {ram_used_gb}GB / {ram_total_gb}GB used ({vm.percent}%)")
        except Exception as exc:
            return f"Could not read system info: {exc}"

    # 5. Active Apps
    if act in ("active_apps", "running_apps", "processes"):
        try:
            import psutil
            apps = []
            for p in psutil.process_iter(["name"]):
                try:
                    name = p.info["name"]
                    if name and name.endswith(".exe") and name.lower() not in (
                        "svchost.exe", "system", "registry", "smss.exe", "csrss.exe", "services.exe", "lsass.exe", "conhost.exe"
                    ):
                        apps.append(name.replace(".exe", ""))
                except Exception:
                    continue
            unique_top = sorted(list(set(apps)))[:15]
            return "Active applications: " + ", ".join(unique_top)
        except Exception as exc:
            return f"Could not list active applications: {exc}"

    return f"Unknown system_control action '{action}'. Valid actions: volume_up, volume_down, mute, lock, battery, system_info, active_apps."


def register_desktop_tools(registry: ToolRegistry) -> None:
    registry.register(Tool(
        name="open_app",
        description="Launches or opens any Windows desktop application (e.g. notepad, code/vscode, chrome, msedge, spotify, calc/calculator, explorer, terminal/powershell, taskmgr, settings) on the user's PC.",
        params_schema={
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Name of the application to open (e.g. 'notepad', 'code', 'chrome', 'calculator', 'spotify', 'explorer', 'settings').",
                },
                "args": {
                    "type": "string",
                    "description": "Optional arguments or file path to pass to the application.",
                    "default": "",
                },
            },
            "required": ["app_name"],
        },
        handler=open_app,
        risk="auto",
    ))

    registry.register(Tool(
        name="open_url",
        description="Opens a website URL or performs a search directly in the user's default web browser (supports YouTube music/video search, Google search, GitHub, etc.).",
        params_schema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The web URL to open (e.g. 'https://github.com', 'https://youtube.com'). Optional if search_query is provided.",
                    "default": "",
                },
                "search_query": {
                    "type": "string",
                    "description": "Query to search on Google or YouTube (e.g. 'lofi hip hop chill music', 'python tutorial').",
                    "default": "",
                },
                "platform": {
                    "type": "string",
                    "description": "Target platform: 'youtube', 'google', or 'web'. Default 'web'.",
                    "default": "web",
                },
            },
            "required": [],
        },
        handler=open_url,
        risk="auto",
    ))

    registry.register(Tool(
        name="system_control",
        description="Controls Windows OS system hardware and state: 'volume_up', 'volume_down', 'mute', 'unmute', 'lock' (lock PC), 'battery' (battery % and status), 'system_info' (CPU, RAM, OS specs), 'active_apps' (list running apps).",
        params_schema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "The action to execute: 'volume_up', 'volume_down', 'mute', 'unmute', 'lock', 'battery', 'system_info', 'active_apps'.",
                    "enum": ["volume_up", "volume_down", "mute", "unmute", "lock", "battery", "system_info", "active_apps"],
                },
                "value": {
                    "type": "string",
                    "description": "Optional parameter for the action.",
                    "default": "",
                },
            },
            "required": ["action"],
        },
        handler=system_control,
        risk="auto",
    ))
