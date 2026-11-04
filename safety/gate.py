"""SafetyGate — allow/ask/block: config policy + path zones + boundary + web approval + taint.

Zones inside LUMI home (allowed_paths[0]):
  * workspace/  -> LUMI yahan khud likh sakti hai (write = auto jab tak turn tainted na ho)
  * baaki sab   -> code/config/DB = PROTECTED: write/delete hamesha block
    (prompt injection se LUMI apna safety gate ya config nahi badal sakti)
Other allowed roots (e.g. Downloads) follow config permissions (ask).
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

from safety.audit import AuditLog
from tools.files import boundary_message, resolve_within

VALID = {"auto", "ask", "block"}
WORKSPACE_DIR = "workspace"          # LUMI ka sandbox — home ke andar
WRITE_TOOLS = {"write_file", "edit_file", "delete_file"}


class ApprovalManager:
    """Thread-safe store for pending web / remote approvals."""

    def __init__(self) -> None:
        self._pending: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create(self, tool_name: str, args: dict) -> tuple[str, threading.Event]:
        aid = uuid.uuid4().hex[:8]
        evt = threading.Event()
        with self._lock:
            self._pending[aid] = {
                "id": aid,
                "tool": tool_name,
                "args": args,
                "event": evt,
                "approved": False,
                "resolved": False,
                "created_at": time.time(),
            }
        return aid, evt

    def resolve(self, aid: str, approved: bool) -> bool:
        with self._lock:
            entry = self._pending.get(aid)
            if not entry or entry["resolved"]:
                return False
            entry["approved"] = bool(approved)
            entry["resolved"] = True
            entry["event"].set()
            return True

    def wait(self, aid: str, timeout: float = 60.0) -> bool:
        with self._lock:
            entry = self._pending.get(aid)
        if not entry:
            return False
        signaled = entry["event"].wait(timeout=timeout)
        with self._lock:
            entry = self._pending.pop(aid, None)
            if not signaled or not entry:
                return False
            return bool(entry.get("approved", False))

    def list_pending(self) -> list[dict]:
        with self._lock:
            return [
                {"id": k, "tool": v["tool"], "args": v["args"], "created_at": v["created_at"]}
                for k, v in self._pending.items() if not v["resolved"]
            ]


class SafetyGate:
    def __init__(self, config: dict,
                 asker: Callable[[str, dict], bool] | None = None,
                 audit: AuditLog | None = None,
                 is_web: bool = False):
        self.perms = dict(config.get("permissions") or {})
        self.allowed_paths = list(config.get("allowed_paths") or [])
        self.asker = asker or (lambda *_: False)   # default NO if no UI attached
        self.audit = audit
        self.is_web = is_web
        self.approval_mgr = ApprovalManager()

    def _policy(self, tool_name: str, risk: str) -> str:
        # per-tool config override wins, else tool's own risk default;
        # unknown value = ask (fail-safe, never silent allow)
        raw = str(self.perms.get(tool_name, risk)).lower()
        return raw if raw in VALID else "ask"

    # -- zones -------------------------------------------------------------
    @property
    def home(self) -> str:
        return self.allowed_paths[0] if self.allowed_paths else ""

    def workspace_path(self) -> Path | None:
        if not self.home:
            return None
        return Path(self.home).expanduser().resolve() / WORKSPACE_DIR

    def zone(self, path: str) -> str:
        """'workspace' | 'core' (protected, LUMI home) | 'other'."""
        if not self.home or resolve_within(path, [self.home]) is None:
            return "other"
        target = Path(path).expanduser().resolve()
        try:
            target.relative_to(self.workspace_path())
            return "workspace"
        except ValueError:
            return "core"

    def check(self, tool_name: str, risk: str, session_id: str = "",
              args: dict | None = None, tainted: bool = False) -> tuple[str, str]:
        """Returns (allow|ask|block, reason). Block decisions logged here."""
        args = args or {}
        policy = self._policy(tool_name, risk)
        path = str(args.get("path", ""))
        if path and tool_name in WRITE_TOOLS:
            if resolve_within(path, self.allowed_paths) is None:
                self.log(session_id, tool_name, args, "block",
                         "boundary: allowed_paths ke bahar")
                return "block", "boundary"
            zone = self.zone(path)
            if zone == "core":
                self.log(session_id, tool_name, args, "block",
                         "protected: LUMI ka apna code/config")
                return "block", "protected"
            if zone == "workspace" and tool_name in {"write_file", "edit_file"} and policy != "block":
                if tainted and policy != "auto":
                    return "ask", "taint:untrusted_data_in_turn"
                return "allow", "override:write_in_workspace"
        if policy == "block":
            self.log(session_id, tool_name, args, "block", "policy:block")
            return "block", "policy"
        if tainted and (tool_name in WRITE_TOOLS or tool_name == "register_project"):
            return "ask", "taint:untrusted_data_in_turn"
        if policy == "auto":
            return "allow", "policy:auto"
        return "ask", "policy:ask"

    def block_message(self, reason: str) -> str:
        if reason == "boundary":
            return boundary_message(self.allowed_paths)
        if reason == "protected":
            return (f"Blocked: ye LUMI ka apna code/config hai — main ise nahi "
                    f"badal sakti. Likhna ho toh '{self.workspace_path()}' "
                    "folder use karo.")
        return "Blocked by safety gate — config.yaml permissions me ye tool block hai."

    def prepare_approval(self, tool_name: str, args: dict) -> str | None:
        """In web mode, generates a pending approval ID for SSE client."""
        if not self.is_web:
            return None
        aid, _ = self.approval_mgr.create(tool_name, args)
        return aid

    def wait_approval(self, aid: str, timeout: float = 60.0, session_id: str = "",
                      tool_name: str = "", args: dict | None = None) -> bool:
        approved = self.approval_mgr.wait(aid, timeout=timeout)
        if not approved:
            self.log(session_id, tool_name, args or {}, "ask_no",
                     "web user refused or timed out")
        return approved

    def resolve_approval(self, aid: str, approved: bool) -> bool:
        return self.approval_mgr.resolve(aid, approved)

    def confirm(self, tool_name: str, args: dict, session_id: str = "") -> bool:
        """Interactive y/N prompt (default NO). Logs ask_no when refused;
        ask_yes is logged by the orchestrator together with the result."""
        try:
            approved = bool(self.asker(tool_name, args))
        except (EOFError, KeyboardInterrupt):
            approved = False
        if not approved:
            self.log(session_id, tool_name, args, "ask_no", "user refused")
        return approved

    def log(self, session_id: str, tool: str, args: dict, decision: str,
            summary: str, retry_used: int = 0) -> None:
        if self.audit:
            self.audit.log(session_id, tool, args, decision, summary, retry_used)

    @staticmethod
    def fmt_args(args: dict) -> str:
        return json.dumps(args, ensure_ascii=False, default=str)
