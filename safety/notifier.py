"""Alert notifier — pluggable channels (console/db/web/desktop/telegram-stub).
v1 = NOTIFY ONLY: alert user ko dikhata hai; LUMI khud kuch stop NAHI karti
(req #4). Dedupe mandatory: same dedupe_key within cooldown = suppressed."""

from __future__ import annotations

import sqlite3
import subprocess
import threading
from datetime import datetime, timedelta
from pathlib import Path

STUB = "phase5 hook, not wired yet"        # telegram integration point (Phase 5)
_ANSI = {"WARN": "\033[33m", "CRITICAL": "\033[31m", "INFO": "\033[36m"}
_RESET = "\033[0m"
_GLYPH = {"WARN": "⚠", "CRITICAL": "🔴", "INFO": "·"}


def ensure_table(db_path) -> None:
    if not db_path:
        return
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
            severity TEXT NOT NULL, rule TEXT NOT NULL,
            message TEXT NOT NULL, dedupe_key TEXT NOT NULL)""")


def recent_alerts(db_path, limit: int = 10,
                  active_window_min: int | None = None) -> list[dict]:
    """CLI /alerts + /api/alerts ka source. active_window_min = banner filter."""
    if not db_path:
        return []
    try:
        ensure_table(db_path)
        cutoff, q, args = None, ("SELECT ts, severity, rule, message FROM alerts"), []
        if active_window_min is not None:
            cutoff = (datetime.now()
                      - timedelta(minutes=int(active_window_min))
                      ).isoformat(timespec="seconds")
            q += " WHERE ts >= ?"
            args.append(cutoff)
        q += " ORDER BY id DESC LIMIT ?"
        args.append(int(limit))
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True,
                             timeout=5) as conn:
            rows = conn.execute(q, args).fetchall()
    except sqlite3.Error:
        return []                              # table lock/gone = honest empty
    return [dict(zip(("ts", "severity", "rule", "message"), r)) for r in rows]


class Notifier:
    """channels = list of fns(severity, rule, message) — pluggable, fail-silent."""

    def __init__(self, db_path, cooldown_min: int = 30, telegram_ids=None):
        self.db_path = str(db_path)
        self.cooldown_min = int(cooldown_min)
        self.tg_ids = [str(x) for x in (telegram_ids or [])]
        self._tg_missing_logged = False       # token/ids missing = log sirf 1 baar
        ensure_table(self.db_path)
        self.channels = [self.console_notify, self.db_notify, self.web_notify,
                         self.desktop_notify, self.telegram_notify]
        self.web_cache: list[dict] = []       # active-alerts cache (/api/alerts)

    def emit(self, severity: str, rule: str, message: str) -> bool:
        """True = fired, False = dedupe-suppressed. Har channel fail = silent."""
        if self._suppressed(rule):
            print(f"[watchdog] suppressed {rule} (dedupe cooldown "
                  f"{self.cooldown_min}m)")
            return False
        for ch in self.channels:
            try:
                ch(severity, rule, message)
            except Exception:                  # noqa: BLE001 — channel fail = ok
                pass
        return True

    def _suppressed(self, key: str) -> bool:
        """Same dedupe_key last cooldown_min me already fire hua? → skip."""
        try:
            with sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True,
                                 timeout=5) as conn:
                row = conn.execute(
                    "SELECT ts FROM alerts WHERE dedupe_key=?"
                    " ORDER BY id DESC LIMIT 1", (key,)).fetchone()
            if not row:
                return False
            return (datetime.now()
                    - datetime.fromisoformat(row[0])) < timedelta(
                        minutes=self.cooldown_min)
        except (sqlite3.Error, ValueError):
            return False

    # -- channels ---------------------------------------------------------
    def console_notify(self, sev: str, rule: str, msg: str) -> None:
        print(f"{_ANSI.get(sev, '')}{_GLYPH.get(sev, '·')} ALERT [{rule}] "
              f"{msg}{_RESET}")

    def db_notify(self, sev: str, rule: str, msg: str) -> None:
        """Append-only row (dedupe emit() pehle kar chuka hota hai)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO alerts (ts, severity, rule, message, dedupe_key)"
                " VALUES (?,?,?,?,?)",
                (datetime.now().isoformat(timespec="seconds"), sev, rule,
                 msg[:300], rule))

    def web_notify(self, sev: str, rule: str, msg: str) -> None:
        self.web_cache.insert(0, {"ts": datetime.now().isoformat(
            timespec="seconds"), "severity": sev, "rule": rule, "message": msg})
        del self.web_cache[20:]               # cache cap = 20 latest

    def desktop_notify(self, sev: str, rule: str, msg: str) -> None:
        """Best-effort Windows toast — fail = SILENT (crash ZERO)."""
        script = ("[Windows.UI.Notifications.ToastNotificationManager, "
                  "Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null; "
                  "$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent"
                  "('ToastText02'); $t.GetElementsByTagName('text').Item(0).AppendChild("
                  "$t.CreateTextNode('LUMI " + _GLYPH.get(sev, "") + " " + rule + "')) | Out-Null; "
                  "$t.GetElementsByTagName('text').Item(1).AppendChild("
                  "$t.CreateTextNode('" + msg.replace("'", "").replace("`", "")[:120] + "')) | Out-Null; "
                  "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
                  "'LUMI').Show([Windows.UI.Notifications.ToastNotification]::new($t))")
        subprocess.run(["powershell", "-NoProfile", "-Command", script],
                       capture_output=True, timeout=8)

    def telegram_notify(self, sev: str, rule: str, msg: str) -> str:
        """REAL wire (Task R): allowlist sabko, prefix ⚠/🔴. Dedupe DB layer pe.
        Token/allowlist missing = silent skip (log once). Integration point:
        interface/telegram_bot.send_text (Phase 5 me same, abhi wired hai)."""
        import os
        from interface.telegram_bot import send_text
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not token or not self.tg_ids:
            if not self._tg_missing_logged:
                self._tg_missing_logged = True
                print("[watchdog->telegram] token/allowlist missing — skip (once)")
            return STUB
        line = (f"{'🔴' if sev == 'CRITICAL' else '⚠'} {sev} [{rule}] {msg}")
        ok = [cid for cid in self.tg_ids if send_text(token, cid, line)]
        return f"sent {len(ok)}/{len(self.tg_ids)}"
