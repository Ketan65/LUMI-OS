"""Shared fixtures — project root on sys.path, fake brain, throwaway orchestrator."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brain.base import Brain, BrainReply  # noqa: E402


class FakeBrain(Brain):
    """Scripted brain: script = list of BrainReply, last one repeats."""

    def __init__(self, script=None, delay=0.0):
        self.script = list(script or [BrainReply(text="ok")])
        self.calls = 0
        self.delay = delay
        self.last_provider = "fake"
        self.last_model = "fake-1"
        self.max_concurrent = 0
        self._active = 0

    def chat(self, messages, tools=None, on_token=None, temperature=None):
        import threading
        import time
        lock = self.__dict__.setdefault("_l", threading.Lock())
        with lock:
            self._active += 1
            self.max_concurrent = max(self.max_concurrent, self._active)
        try:
            time.sleep(self.delay)
            reply = self.script[min(self.calls, len(self.script) - 1)]
            self.calls += 1
            if on_token and reply.text:
                on_token(reply.text)
            return reply
        finally:
            with lock:
                self._active -= 1


@pytest.fixture
def home(tmp_path):
    """Fake LUMI home: <tmp>/lumi with workspace/ + some 'code'."""
    h = tmp_path / "lumi"
    (h / "workspace").mkdir(parents=True)
    (h / "safety").mkdir()
    (h / "safety" / "gate.py").write_text("# gate", encoding="utf-8")
    (h / "config.yaml").write_text("a: 1", encoding="utf-8")
    return h


@pytest.fixture
def downloads(tmp_path):
    d = tmp_path / "Downloads"
    d.mkdir()
    return d
