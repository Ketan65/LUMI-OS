"""Proactive Assistant — LUMI khud se baat shuru karein (JARVIS style).

Triggers:
  - Time-based (good morning, lunch reminder, etc.)
  - Event-based (app opened, file changed, etc.)
  - Context-based (screen shows something important)

Runs in background thread, checks conditions, speaks via TTS.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Optional

import yaml


def load_config() -> dict:
    try:
        with open("config.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


class ProactiveAssistant:
    """
    Background assistant jo conditions check karta hai aur LUMI ko bolne ka kehta hai.
    Callback: on_speak(text) — jo TTS pipeline se juda hoga.
    """

    def __init__(self, on_speak: Callable[[str], None], identity: dict,
                 cfg: Optional[dict] = None):
        self.on_speak = on_speak
        self.identity = identity
        self.cfg = cfg or load_config()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_spoken: dict[str, float] = {}
        self._cooldown = 300  # 5 min between same proactive message

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[proactive] JARVIS proactive mode started.")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _loop(self) -> None:
        while self._running:
            try:
                self._check_triggers()
            except Exception as exc:
                print(f"[proactive] Error: {exc}")
            time.sleep(60)  # check every minute

    def _check_triggers(self) -> None:
        import datetime

        now = datetime.datetime.now()
        hour = now.hour
        name = self.identity.get("user", {}).get("name", "Sir")

        # Good morning (once per day)
        if hour == 8 and self._should_speak("morning"):
            self.on_speak(f"Good morning {name}. Main LUMI hoon, aapka assistant. Aaj kya plan hai?")
            self._mark_spoken("morning")

        # Lunch reminder (once per day)
        if hour == 13 and self._should_speak("lunch"):
            self.on_speak(f"Sir, lunch ka time ho gaya hai. Thoda break lein aur khana kha lein.")
            self._mark_spoken("lunch")

        # Evening wrap-up
        if hour == 19 and self._should_speak("evening"):
            self.on_speak(f"Good evening {name}. Kaam khatam hone wala hai. Kuch pending task hai jo main yaad rakhun?")
            self._mark_spoken("evening")

        # Night
        if hour == 23 and self._should_speak("night"):
            self.on_speak(f"Raat ho gayi {name}. Sone ka time hai ya kuch aur kaam baki hai?")
            self._mark_spoken("night")

    def _should_speak(self, key: str) -> bool:
        if not self.identity.get("preferences", {}).get("proactive", True):
            return False
        last = self._last_spoken.get(key, 0)
        return (time.time() - last) > self._cooldown

    def _mark_spoken(self, key: str) -> None:
        self._last_spoken[key] = time.time()

    def notify(self, message: str, key: str | None = None) -> None:
        """Manually trigger a proactive message (e.g., from screen monitor)."""
        if key and not self._should_speak(key):
            return
        self.on_speak(message)
        if key:
            self._mark_spoken(key)
