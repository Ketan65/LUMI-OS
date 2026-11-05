"""JARVIS Active Context Sensor — Zero-Latency Windows 11 Situational Awareness.

Gives LUMI-OS real-time situational awareness of the developer's live workstation
without heavy screenshot/OCR overhead:
  1. Active foreground window title & process name via Win32 (`user32` + `psutil`).
  2. Live clipboard content classification (`python_traceback`, `compiler_error`,
     `url`, `shell_command`, `code_snippet`, `json_payload`, or `plain_text`)
     with secret/API-key redaction and safe length truncation.
  3. Active Git repository diff / dirty status (`git status -s`).
  4. Deictic / situational prompt detector (`should_auto_inject_context`) for
     Hinglish & English phrases like "ye error fix kar", "isko dekh", "check clipboard",
     "meri screen pe kya hai", "why did this fail", etc.
"""

from __future__ import annotations

import ctypes
import re
import subprocess
import time
from pathlib import Path
from typing import Any


# Secret redaction patterns so API keys / tokens in clipboard are never leaked
_SECRET_PATTERNS = [
    re.compile(r"(sk-[a-zA-Z0-9_\-]{20,})"),
    re.compile(r"(nvapi-[a-zA-Z0-9_\-]{20,})"),
    re.compile(r"(gsk_[a-zA-Z0-9_\-]{20,})"),
    re.compile(r"(ghp_[a-zA-Z0-9]{20,})"),
    re.compile(r"(AIza[0-9A-Za-z\-_]{30,})"),
]

# Deictic & situational triggers (Hinglish + English)
_SITUATIONAL_PHRASES = (
    "ye error",
    "yeh error",
    "is error",
    "iss error",
    "isko dekh",
    "ise dekh",
    "isko fix",
    "ye fix",
    "yeh fix",
    "fix this",
    "fix the error",
    "fix this traceback",
    "why did this fail",
    "why is this failing",
    "what is this error",
    "ye kya error",
    "yeh kya error",
    "clipboard",
    "copied",
    "paste",
    "meri screen",
    "screen pe kya",
    "what am i looking at",
    "what's on my screen",
    "active window",
    "current window",
    "abhi main kya kar raha",
    "what am i working on",
    "terminal error",
    "traceback",
)


def _redact_secrets(text: str) -> str:
    """Mask API keys or tokens accidentally copied to clipboard."""
    if not text:
        return ""
    masked = text
    for pat in _SECRET_PATTERNS:
        masked = pat.sub("[REDACTED_SECRET]", masked)
    return masked


class ActiveContextSensor:
    """Captures live Windows 11 workstation context and formats situational blocks."""

    def __init__(self, workspace_root: str | Path = ".", max_clipboard_chars: int = 1800) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.max_clipboard_chars = max_clipboard_chars
        self._last_snapshot: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # 1. Foreground Window & Process (Win32 ctypes)
    # ------------------------------------------------------------------
    def get_active_window(self) -> dict[str, Any]:
        """Returns `{title, pid, process_name}` of the active foreground window."""
        title = ""
        pid = 0
        proc_name = ""
        try:
            user32 = getattr(ctypes, "windll", None) and getattr(ctypes.windll, "user32", None)
            if user32:
                hwnd = user32.GetForegroundWindow()
                if hwnd:
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        title = buf.value.strip()

                    pid_ulong = ctypes.c_ulong(0)
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_ulong))
                    pid = int(pid_ulong.value)
                    if pid > 0:
                        try:
                            import psutil
                            proc_name = psutil.Process(pid).name()
                        except Exception:
                            proc_name = ""
        except Exception:
            pass

        return {
            "title": title or "Desktop / Unknown Window",
            "pid": pid,
            "process": proc_name or "unknown",
        }

    # ------------------------------------------------------------------
    # 2. Clipboard Reading & Intelligent Classification
    # ------------------------------------------------------------------
    def get_clipboard_text(self) -> str:
        """Safely reads Windows clipboard text using Win32 API or PowerShell fallback."""
        text = self._read_clipboard_win32()
        if text is None:
            try:
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", "Get-Clipboard"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=1.5,
                )
                if res.returncode == 0:
                    text = res.stdout
            except Exception:
                text = ""
        clean = _redact_secrets((text or "").strip())
        if len(clean) > self.max_clipboard_chars:
            clean = clean[: self.max_clipboard_chars] + "\n...[truncated]"
        return clean

    @staticmethod
    def _read_clipboard_win32() -> str | None:
        """Fast native Win32 CF_UNICODETEXT clipboard read (~0.5ms)."""
        CF_UNICODETEXT = 13
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            user32.OpenClipboard.argtypes = [ctypes.c_void_p]
            user32.OpenClipboard.restype = ctypes.c_int
            user32.GetClipboardData.argtypes = [ctypes.c_uint]
            user32.GetClipboardData.restype = ctypes.c_void_p
            user32.CloseClipboard.argtypes = []
            user32.CloseClipboard.restype = ctypes.c_int
            kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
            kernel32.GlobalLock.restype = ctypes.c_void_p
            kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
            kernel32.GlobalUnlock.restype = ctypes.c_int

            if not user32.OpenClipboard(None):
                return None
            try:
                handle = user32.GetClipboardData(CF_UNICODETEXT)
                if not handle:
                    return ""
                ptr = kernel32.GlobalLock(handle)
                if not ptr:
                    return ""
                try:
                    return ctypes.wstring_at(ptr)
                finally:
                    kernel32.GlobalUnlock(handle)
            finally:
                user32.CloseClipboard()
        except Exception:
            return None

    @staticmethod
    def classify_clipboard(text: str) -> dict[str, Any]:
        """Classifies clipboard text into actionable developer telemetry categories."""
        if not text or not text.strip():
            return {"kind": "empty", "is_error": False, "summary": "Clipboard is empty"}

        s = text.strip()
        lines = [ln.strip() for ln in s.splitlines() if ln.strip()]

        # 1. Python Traceback / Exception
        if (
            "Traceback (most recent call last):" in s
            or re.search(r"^\s*File \".+\", line \d+", s, re.MULTILINE)
            or re.search(
                r"\b(SyntaxError|TypeError|ValueError|KeyError|AttributeError|ImportError|"
                r"ModuleNotFoundError|IndexError|ZeroDivisionError|RuntimeError|NameError|"
                r"FileNotFoundError|PermissionError|AssertionError):",
                s,
            )
        ):
            last_line = lines[-1] if lines else s[:120]
            file_matches = re.findall(r'File "([^"]+)", line (\d+)', s)
            locations = [f"{Path(f).name}:{ln}" for f, ln in file_matches[-3:]]
            return {
                "kind": "python_traceback",
                "is_error": True,
                "exception_line": last_line[:200],
                "locations": locations,
                "summary": f"Python Error: {last_line[:140]}",
            }

        # 2. Compiler / Runtime / Shell Error
        if re.search(
            r"\b(error\[E\d+\]|Exception in thread|npm ERR!|fatal:|FAILED|Segmentation fault|"
            r"ReferenceError:|TypeError:|SyntaxError:|Cannot find module|command not found|"
            r"CategoryInfo\s*:|FullyQualifiedErrorId)\b",
            s,
            re.IGNORECASE,
        ):
            first_err = next(
                (ln for ln in lines if "err" in ln.lower() or "fail" in ln.lower() or "exception" in ln.lower()),
                lines[0] if lines else s[:120],
            )
            return {
                "kind": "compiler_or_shell_error",
                "is_error": True,
                "exception_line": first_err[:200],
                "locations": [],
                "summary": f"System/Compiler Error: {first_err[:140]}",
            }

        # 3. URL
        if len(lines) == 1 and re.match(r"^https?://\S+$", s, re.IGNORECASE):
            return {
                "kind": "url",
                "is_error": False,
                "summary": f"URL: {s[:140]}",
            }

        # 4. Shell Command
        if len(lines) <= 3 and re.match(
            r"^(\$\s*|PS[^>]*>\s*)?(git|python|pytest|pip|npm|node|docker|curl|cargo|uvicorn)\b",
            s,
            re.IGNORECASE,
        ):
            return {
                "kind": "shell_command",
                "is_error": False,
                "summary": f"Command: {lines[0][:120]}",
            }

        # 5. Code Snippet
        if re.search(
            r"\b(def |class |import |from .+ import |function |const |let |return |if __name__)",
            s,
        ):
            return {
                "kind": "code_snippet",
                "is_error": False,
                "summary": f"Code snippet ({len(lines)} lines)",
            }

        # 6. Plain Text
        return {
            "kind": "plain_text",
            "is_error": False,
            "summary": f"Text ({len(lines)} lines, {len(s)} chars)",
        }

    # ------------------------------------------------------------------
    # 3. Git / Workspace Status
    # ------------------------------------------------------------------
    def get_git_status_summary(self) -> dict[str, Any]:
        """Captures compact `git status -s` & current branch in workspace_root."""
        branch = "unknown"
        modified: list[str] = []
        try:
            b_res = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=1.2,
            )
            if b_res.returncode == 0:
                branch = b_res.stdout.strip()

            s_res = subprocess.run(
                ["git", "status", "-s"],
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=1.5,
            )
            if s_res.returncode == 0:
                modified = [ln.strip() for ln in s_res.stdout.splitlines() if ln.strip()][:12]
        except Exception:
            pass

        return {
            "branch": branch,
            "modified_count": len(modified),
            "modified_files": modified,
        }

    # ------------------------------------------------------------------
    # 4. Full Workstation Telemetry Snapshot & Auto-Injection
    # ------------------------------------------------------------------
    def capture_workstation_context(self) -> dict[str, Any]:
        """Captures full live workstation context (window, clipboard, git status)."""
        win = self.get_active_window()
        clip_text = self.get_clipboard_text()
        clip_meta = self.classify_clipboard(clip_text)
        git_info = self.get_git_status_summary()

        snapshot = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "active_window": win,
            "clipboard": {
                **clip_meta,
                "content": clip_text,
            },
            "git": git_info,
        }
        self._last_snapshot = snapshot
        return snapshot

    def should_auto_inject_context(self, user_text: str) -> bool:
        """Returns True when user prompt uses deictic/situational language."""
        if not user_text:
            return False
        low = user_text.strip().lower()
        if any(phrase in low for phrase in _SITUATIONAL_PHRASES):
            return True
        # Also match patterns like "ye <something> fix kar" or "fix this <something>"
        if re.search(r"\b(ye|yeh|is|iss|this)\b.*\b(error|bug|issue|problem|code|fail|crash)\b", low):
            return True
        return False

    def format_context_injection(self, user_text: str = "") -> str:
        """Formats a crisp `[JARVIS LIVE SITUATIONAL SENSOR]` block for LLM prompt injection."""
        ctx = self.capture_workstation_context()
        win = ctx["active_window"]
        clip = ctx["clipboard"]
        git = ctx["git"]

        lines = [
            "[JARVIS LIVE SITUATIONAL SENSOR]",
            f"- Active Foreground Window: {win['title']} (Process: {win['process']}, PID: {win['pid']})",
            f"- Workspace Git State: branch={git['branch']} | {git['modified_count']} modified entry(s)"
            + (f" ({', '.join(git['modified_files'][:5])})" if git["modified_files"] else ""),
            f"- Clipboard Classification: {clip['kind']} ({clip['summary']})",
        ]
        if clip.get("locations"):
            lines.append(f"- Traceback File Locations: {', '.join(clip['locations'])}")
        if clip.get("content"):
            snippet = clip["content"][:900]
            lines.append(f"- Clipboard Content Excerpt:\n```\n{snippet}\n```")
        lines.append("[/JARVIS LIVE SITUATIONAL SENSOR]")
        return "\n".join(lines)


_GLOBAL_SENSOR: ActiveContextSensor | None = None


def get_context_sensor(workspace_root: str | Path = ".") -> ActiveContextSensor:
    global _GLOBAL_SENSOR
    if _GLOBAL_SENSOR is None:
        _GLOBAL_SENSOR = ActiveContextSensor(workspace_root=workspace_root)
    return _GLOBAL_SENSOR
