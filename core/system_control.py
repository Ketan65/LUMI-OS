"""System Control — LUMI se PC control karwaein (Windows native).

Apps open karna, files read/write karna, shell commands, system info.
Sirf local — koi internet nahi chahiye.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def open_app(app_name: str) -> str:
    """Koi bhi application kholein (chrome, vscode, telegram, notepad, etc.)."""
    app_name = app_name.lower().strip()
    common = {
        "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "google chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "vscode": r"C:\Users\%USERNAME%\AppData\Local\Programs\Microsoft VS Code\Code.exe",
        "code": r"C:\Users\%USERNAME%\AppData\Local\Programs\Microsoft VS Code\Code.exe",
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "paint": "mspaint.exe",
        "telegram": "telegram.exe",
        "discord": "discord.exe",
        "spotify": "spotify.exe",
        "obsidian": "obsidian.exe",
    }

    key = app_name
    if key in common:
        path = os.path.expandvars(common[key])
        try:
            os.startfile(path)
            return f"{app_name} open kar diya gaya hai, Sir."
        except Exception as exc:
            return f"{app_name} kholne mein dikkat aayi: {exc}"

    # Generic — try to start as command
    try:
        os.startfile(app_name)
        return f"{app_name} open kar diya gaya hai, Sir."
    except Exception as exc:
        return f"{app_name} nahi mila ya khol nahi sakta: {exc}"


def open_file(file_path: str) -> str:
    """Koi bhi file uske default app mein kholein."""
    p = Path(file_path).expanduser()
    if not p.exists():
        return f"File nahi milti: {file_path}"
    try:
        os.startfile(str(p))
        return f"File open kar di: {p.name}"
    except Exception as exc:
        return f"File kholne mein error: {exc}"


def open_folder(folder_path: str) -> str:
    """Folder Explorer mein kholein."""
    p = Path(folder_path).expanduser()
    if not p.exists() or not p.is_dir():
        return f"Folder nahi milta: {folder_path}"
    try:
        os.startfile(str(p))
        return f"Folder open kar di: {p.name}"
    except Exception as exc:
        return f"Folder kholne mein error: {exc}"


def run_shell(command: str) -> str:
    """Windows shell command chalayein (dir, ipconfig, tasklist, etc.)."""
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
        output = result.stdout.strip()
        if result.stderr.strip():
            output += "\n" + result.stderr.strip()
        return output or "Command chal gayi, koi output nahi."
    except subprocess.TimeoutExpired:
        return "Command timeout ho gayi (30s limit)."
    except Exception as exc:
        return f"Shell error: {exc}"


def read_file(file_path: str, max_chars: int = 2000) -> str:
    """Text file padhein."""
    p = Path(file_path).expanduser()
    if not p.exists():
        return f"File nahi milti: {file_path}"
    try:
        content = p.read_text(encoding="utf-8", errors="ignore")[:max_chars]
        return content or "File khaali hai."
    except Exception as exc:
        return f"File padhne mein error: {exc}"


def write_file(file_path: str, content: str) -> str:
    """File mein likhein."""
    p = Path(file_path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(content, encoding="utf-8")
        return f"File save kar di: {p.name}"
    except Exception as exc:
        return f"File likhne mein error: {exc}"


def list_folder(folder_path: str) -> str:
    """Folder ki content dikhayein."""
    p = Path(folder_path).expanduser()
    if not p.exists() or not p.is_dir():
        return f"Folder nahi milta: {folder_path}"
    try:
        items = list(p.iterdir())
        if not items:
            return "Folder khaali hai."
        lines = [f"DIR {p.name} ({len(items)} items):"]
        for item in sorted(items, key=lambda x: (not x.is_dir(), x.name.lower())):
            mark = "DIR" if item.is_dir() else "FILE"
            lines.append(f"  [{mark}] {item.name}")
        return "\n".join(lines[:50])
    except Exception as exc:
        return f"Folder padhne mein error: {exc}"


def system_info() -> str:
    """PC ka basic info — RAM, CPU, etc."""
    import platform

    lines = []
    lines.append(f"Device: {platform.node()}")
    lines.append(f"OS: {platform.system()} {platform.release()}")
    lines.append(f"Processor: {platform.processor()}")
    try:
        import psutil

        mem = psutil.virtual_memory()
        lines.append(f"RAM: {mem.total // (1024**3)} GB total, {mem.available // (1024**3)} GB available")
        lines.append(f"CPU usage: {psutil.cpu_percent(interval=0.5)}%")
    except Exception:
        pass
    return "\n".join(lines)


def get_clipboard() -> str:
    """Clipboard ka text padhein."""
    try:
        import pyperclip

        return pyperclip.paste()
    except Exception:
        return "pyperclip install nahi hai ya clipboard access nahi mila."


def set_clipboard(text: str) -> str:
    """Clipboard mein likhein."""
    try:
        import pyperclip

        pyperclip.copy(text)
        return "Clipboard mein copy kar diya."
    except Exception as exc:
        return f"Clipboard error: {exc}"
