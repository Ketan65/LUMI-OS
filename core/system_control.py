"""System Control — Hardened & Fortress-Grade (Windows native).

Apps open karna, files read/write karna, shell commands, system info.
SECURITY ENFORCED:
  - Whitelist-only app launching (zero arbitrary startfile execution)
  - Strict command execution guardrails (blocks reverse shells, format, credential dumping, powershell -enc)
  - Path traversal containment within allowed roots
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

# Allowed safe application registry (lowercase keys)
SAFE_APP_REGISTRY: dict[str, str] = {
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "google chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "vscode": r"C:\Users\%USERNAME%\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "code": r"C:\Users\%USERNAME%\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "telegram": "telegram.exe",
    "discord": "discord.exe",
    "spotify": "spotify.exe",
    "obsidian": "obsidian.exe",
    "explorer": "explorer.exe",
    "terminal": "wt.exe",
    "task manager": "taskmgr.exe",
}

# Forbidden command execution patterns (Security Red Team Guardrails)
FORBIDDEN_SHELL_PATTERNS = [
    re.compile(r"\bformat\s+[a-zA-Z]:", re.I),
    re.compile(r"\bdel\s+.*[/\\](s|q)", re.I),
    re.compile(r"\brmdir\s+.*[/\\](s|q)", re.I),
    re.compile(r"\bdiskpart\b", re.I),
    re.compile(r"\bpkgmgr\b", re.I),
    re.compile(r"\breg\s+(delete|save\s+.*sam)", re.I),
    re.compile(r"\b(downloadstring|invoke-expression|\biex\b)", re.I),
    re.compile(r"\bpowershell.*(-e|-enc|-encodedcommand)\b", re.I),
    re.compile(r"\b(curl|wget)\b.*\|\s*(bash|sh|powershell|cmd)", re.I),
    re.compile(r"\b(nc|ncat)\s+.*-e", re.I),
    re.compile(r"\b(mimikatz|sekurlsa|procdump)\b", re.I),
    re.compile(r"\bnet\s+user\s+.*\/add", re.I),
    re.compile(r"\bnet\s+localgroup\s+administrators\s+.*\/add", re.I),
]

SENSITIVE_PATH_PATTERNS = [
    re.compile(r"[/\\](windows|system32|syswow64)[/\\]", re.I),
    re.compile(r"[/\\]\.ssh[/\\]", re.I),
    re.compile(r"[/\\]\.aws[/\\]", re.I),
    re.compile(r"\.env($|[/\\])", re.I),
    re.compile(r"id_rsa", re.I),
]


def _is_safe_path(target_path: str | Path, write: bool = False) -> bool:
    """Ensure path is within current working directory or allowed sandbox, and not a sensitive system file."""
    try:
        resolved = Path(target_path).expanduser().resolve()
        cwd = Path(".").resolve()
        downloads = (Path.home() / "Downloads").resolve()

        # Check allowed boundaries
        inside_cwd = False
        try:
            resolved.relative_to(cwd)
            inside_cwd = True
        except ValueError:
            pass

        inside_downloads = False
        try:
            resolved.relative_to(downloads)
            inside_downloads = True
        except ValueError:
            pass

        if not (inside_cwd or inside_downloads):
            return False

        # Block sensitive OS and credential paths
        path_str = str(resolved).lower()
        if any(p.search(path_str) for p in SENSITIVE_PATH_PATTERNS):
            return False

        return True
    except Exception:
        return False


def open_app(app_name: str) -> str:
    """Whitelist-only safe application launcher. Blocks arbitrary executable/script injection."""
    clean = re.sub(r"[;&|`$><\r\n]", "", str(app_name or "")).strip().lower()
    if not clean:
        return "App name specify kijiye."

    if clean in SAFE_APP_REGISTRY:
        target = os.path.expandvars(SAFE_APP_REGISTRY[clean])
        try:
            os.startfile(target)
            return f"{clean} open kar diya gaya hai, Sir."
        except Exception as exc:
            return f"{clean} kholne mein dikkat aayi: {exc}"

    # Check if user passed a standard safe app name that maps to known utility
    for k, v in SAFE_APP_REGISTRY.items():
        if k in clean:
            target = os.path.expandvars(v)
            try:
                os.startfile(target)
                return f"{k} open kar diya gaya hai, Sir."
            except Exception as exc:
                return f"{k} kholne mein error: {exc}"

    return f"Security Guardrail: '{clean}' allowed safe application registry me nahi hai. Sirf verified apps open kiye ja sakte hain."


def open_file(file_path: str) -> str:
    """Opens a file inside allowed workspace safely."""
    p = Path(file_path).expanduser().resolve()
    if not _is_safe_path(p, write=False):
        return f"Security Blocked: Path boundary ke bahar hai ya sensitive file hai: {file_path}"
    if not p.exists():
        return f"File nahi milti: {p.name}"
    try:
        os.startfile(str(p))
        return f"File open kar di: {p.name}"
    except Exception as exc:
        return f"File kholne mein error: {exc}"


def open_folder(folder_path: str) -> str:
    """Opens a folder inside allowed workspace safely."""
    p = Path(folder_path).expanduser().resolve()
    if not _is_safe_path(p, write=False):
        return f"Security Blocked: Folder boundary ke bahar hai: {folder_path}"
    if not p.exists() or not p.is_dir():
        return f"Folder nahi milta: {folder_path}"
    try:
        os.startfile(str(p))
        return f"Folder open kar di: {p.name}"
    except Exception as exc:
        return f"Folder kholne mein error: {exc}"


def run_shell(command: str) -> str:
    """Windows shell command with strict Red Team command execution guardrails."""
    cmd = (command or "").strip()
    if not cmd:
        return "Command khali hai."

    # Validate against forbidden attack patterns
    for pat in FORBIDDEN_SHELL_PATTERNS:
        if pat.search(cmd):
            return f"Security Guardrail Blocked: Dangerous command pattern detected ({pat.pattern}). Execution prevented."

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=30
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
    """Safe bounded text file reading with directory traversal protection."""
    p = Path(file_path).expanduser().resolve()
    if not _is_safe_path(p, write=False):
        return f"Security Blocked: Access denied to path outside allowed boundary: {file_path}"
    if not p.exists():
        return f"File nahi milti: {file_path}"
    try:
        content = p.read_text(encoding="utf-8", errors="ignore")[:max_chars]
        return content or "File khaali hai."
    except Exception as exc:
        return f"File padhne mein error: {exc}"


def write_file(file_path: str, content: str) -> str:
    """Safe bounded text file writing with system folder protection."""
    p = Path(file_path).expanduser().resolve()
    if not _is_safe_path(p, write=True):
        return f"Security Blocked: Cannot write to path outside allowed workspace: {file_path}"
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(content, encoding="utf-8")
        return f"File save kar di: {p.name}"
    except Exception as exc:
        return f"File likhne mein error: {exc}"


def list_folder(folder_path: str) -> str:
    """Folder content listing with boundary protection."""
    p = Path(folder_path).expanduser().resolve()
    if not _is_safe_path(p, write=False):
        return f"Security Blocked: Access denied to path outside allowed boundary: {folder_path}"
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
    """PC basic system info (RAM, CPU, OS)."""
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
    """Safe clipboard reading."""
    try:
        import pyperclip
        return pyperclip.paste()
    except Exception:
        return "pyperclip install nahi hai ya clipboard access nahi mila."


def set_clipboard(text: str) -> str:
    """Safe clipboard writing."""
    try:
        import pyperclip
        pyperclip.copy(text)
        return "Clipboard mein copy kar diya."
    except Exception as exc:
        return f"Clipboard error: {exc}"
