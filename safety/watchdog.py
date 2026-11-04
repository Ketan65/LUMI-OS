"""Watchdog — periodic anomaly checks, daemon thread (req #11, Task Q).
v1 = NOTIFY ONLY — sirf alert, kuch band nahi (stop = permission, req #4).
Config har loop pe YAML se dobara padhi jaati hai (interval/rules live)."""

from __future__ import annotations

import shutil
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

import yaml


class Watchdog:
    def __init__(self, config_path="config.yaml", emit=None, db_path="",
                 log_paths=None, heartbeat="data/watchdog.heartbeat"):
        self.config_path = Path(config_path)
        self.emit = emit or (lambda *a, **k: False)
        self.db_path = str(db_path)
        self.logs = log_paths or ["data/logs/brain.log", "data/web_out.log"]
        self.heartbeat_path = Path(heartbeat)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- config (har loop pe fresh) --------------------------------------
    def _cfg(self) -> dict:
        try:
            return (yaml.safe_load(self.config_path.read_text(
                encoding="utf-8")) or {}).get("watchdog") or {}
        except Exception:                      # noqa: BLE001 — bad yaml = skip cycle
            return {}

    # -- pure evaluation: breaches list, 0 side effects ------------------
    def run_checks(self, cfg: dict) -> list[tuple[str, str, str]]:
        rules = cfg.get("rules") or {}
        win_e = int(rules.get("error_window_min", 5))
        out: list[tuple[str, str, str]] = []
        # (a) DISK — free <1GB CRITICAL; band <disk_free_min_gb WARN
        try:
            free = shutil.disk_usage("C:/").free / (1 << 30)
            min_gb = float(rules.get("disk_free_min_gb", 5))
            crit = 1.0 if min_gb <= 10 else min_gb * 0.05   # absurd threshold = test band
            if free < crit:
                out.append(("CRITICAL", "disk_free",
                            f"disk free {free:.1f} GB < {crit:.1f} GB"))
            elif free < min_gb:
                out.append(("WARN", "disk_free",
                            f"disk free {free:.1f} GB < {min_gb:g} GB"))
        except OSError:
            pass
        # (b) ERROR BURST — audit table decision=error in window
        n = self._audit_count("error", win_e)
        if n >= int(rules.get("error_burst", 3)):
            out.append(("WARN", "error_burst",
                        f"{n} tool errors in last {win_e}m"))
        # (d) GATE BLOCK BURST
        n = self._audit_count("block", win_e)
        if n >= int(rules.get("gate_block_burst", 5)):
            out.append(("WARN", "gate_block",
                        f"{n} gate blocks in last {win_e}m"))
        # (c) FALLBACK BURST — brain.log FALLBACK lines in window
        n = self._log_count(self.logs[0], int(rules.get("fallback_window_min", 10)),
                            "FALLBACK")
        if n >= int(rules.get("fallback_burst", 3)):
            out.append(("WARN", "fallback_burst",
                        f"{n} local→cloud fallbacks in window"))
        # LLM ERRORS — brain.log " err " burst (same window as errors)
        n = self._log_count(self.logs[0], win_e, " err ")
        if n >= int(rules.get("error_burst", 3)):
            out.append(("WARN", "llm_burst", f"{n} LLM errors in last {win_e}m"))
        # (e) INTEGRITY — friendly DB-error marker in stdout logs (>=1 = WARN)
        n = sum(self._log_count(p, win_e, "memory problem") for p in self.logs)
        if n >= 1:
            out.append(("WARN", "integrity",
                        f"friendly DB error seen {n}x in last {win_e}m"))
        return out

    def _audit_count(self, decision: str, minutes: int) -> int:
        if not self.db_path:
            return 0
        try:
            cutoff = (datetime.now() - timedelta(minutes=int(minutes))
                      ).isoformat(timespec="seconds")
            with sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True,
                                 timeout=5) as conn:
                return conn.execute(
                    "SELECT COUNT(*) FROM tool_calls WHERE decision=? AND ts>=?",
                    (decision, cutoff)).fetchone()[0]
        except sqlite3.Error:
            return 0

    @staticmethod
    def _is_iso(line: str) -> bool:
        return (len(line) > 19 and line[4] == "-" and line[7] == "-"
                and line[10] == "T")

    def _log_count(self, path, minutes: int, marker: str) -> int:
        try:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return 0
        cutoff = (datetime.now() - timedelta(minutes=int(minutes))
                  ).isoformat(timespec="seconds")
        return sum(1 for line in text.splitlines()
                   if marker in line and self._is_iso(line) and line[:19] >= cutoff)

    # -- daemon thread ----------------------------------------------------
    def tick(self) -> int:
        """Ek check cycle: breaches -> emit. Returns fired count (tests)."""
        cfg = self._cfg()
        fired = 0
        if cfg.get("enabled", True):
            for sev, rule, msg in self.run_checks(cfg):
                try:
                    if self.emit(sev, rule, msg):
                        fired += 1
                except Exception:              # noqa: BLE001 — emit fail = skip
                    pass
        return fired

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:                  # noqa: BLE001 — cycle crash = log-free skip
                pass
            self._beat()
            cfg = self._cfg()
            try:
                self._stop.wait(max(2, int(cfg.get("interval_s", 60) or 60)))
            except (TypeError, ValueError):
                self._stop.wait(60)

    def _beat(self) -> None:
        try:
            self.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
            self.heartbeat_path.write_text(
                datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
        except OSError:
            pass

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="lumi-watchdog")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
