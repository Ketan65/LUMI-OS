"""Wake-word detection — openWakeWord (ONNX) with STT-based fallback.

Primary: openWakeWord ONNX models (low-latency, dedicated wake word spotting)
Fallback: Silero VAD + faster-whisper STT transcript match (works with any phrase,
e.g. "Hey LUMI", "Lumi", no custom model needed).

Config: voice.wake_word { enabled, phrase, model, threshold }
"""

from __future__ import annotations

import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable, Optional

import numpy as np


class WakeWordDetector:
    """
    Wake-word detector. Tries openWakeWord (ONNX) first; falls back to
    VAD + STT transcript matching if openWakeWord models can't load.
    """

    def __init__(
        self,
        phrase: str = "hey lumi",
        threshold: float = 0.5,
        cooldown_s: float = 2.0,
        model_path: Optional[str] = None,
    ):
        self.phrase = phrase.lower()
        self.threshold = threshold
        self.cooldown_s = cooldown_s
        self.model_path = model_path
        self._engine: Optional[str] = None  # "openwakeword" | "stt" | None
        self._oww = None
        self._model_names: list[str] = []
        self._last_detection: float = 0.0
        self._callback: Optional[Callable[[], None]] = None
        self._listening = False
        self._thread: Optional[threading.Thread] = None
        self._init_engine()

    # ------------------------------------------------------------------ init

    def _init_engine(self) -> None:
        """Try openWakeWord ONNX; fall back to None (caller handles STT path)."""
        try:
            from openwakeword import Model

            # ONNX framework (tflite-runtime isn't available on Windows)
            kwargs = {"inference_framework": "onnx"}
            if self.model_path:
                p = Path(self.model_path)
                if p.is_file():
                    kwargs["wakeword_models"] = [str(p)]
            self._oww = Model(**kwargs)
            self._engine = "openwakeword"
            self._model_names = list(self._oww.models.keys())
            print(f"[wake] openWakeWord ONNX ready: {self._model_names}")
        except Exception as exc:
            self._engine = None
            self._oww = None
            print(f"[wake] openWakeWord unavailable ({exc}) - using STT-based wake word")

    # ---------------------------------------------------------------- callback

    def on_detect(self, callback: Callable[[], None]) -> None:
        """Register callback fired when wake word is detected."""
        self._callback = callback

    # ---------------------------------------------------------------- audio

    def check_openwakeword(self, pcm16: np.ndarray) -> bool:
        """
        Run openWakeWord on 16-bit PCM audio (16 kHz mono).
        Returns True if wake word detected above threshold.
        """
        if self._engine != "openwakeword" or self._oww is None:
            return False

        now = time.time()
        if now - self._last_detection < self.cooldown_s:
            return False

        try:
            # openWakeWord expects int16, 16 kHz mono, chunks of 1280 samples (80 ms)
            if pcm16.dtype != np.int16:
                pcm16 = pcm16.astype(np.int16)
            scores = self._oww.predict(pcm16, threshold={m: self.threshold for m in self._model_names})
            for name, score in scores.items():
                if score and score >= self.threshold:
                    self._last_detection = now
                    if self._callback:
                        self._callback()
                    return True
        except Exception:
            pass
        return False

    def check_stt_transcript(self, transcript: str) -> bool:
        """STT-based wake word match. Call this from the STT pipeline."""
        now = time.time()
        if now - self._last_detection < self.cooldown_s:
            return False
        t = transcript.lower().strip()
        if self.phrase in t or any(w in t for w in self.phrase.split()):
            self._last_detection = now
            if self._callback:
                self._callback()
            return True
        return False

    # ---------------------------------------------------------------- loop

    def start(self, audio_callback) -> None:
        """Start background listening loop. audio_callback() -> (pcm16_chunk, sample_rate) or None."""
        if self._listening:
            return
        self._listening = True
        self._thread = threading.Thread(target=self._loop, args=(audio_callback,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._listening = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _loop(self, audio_callback) -> None:
        while self._listening:
            try:
                result = audio_callback()
                if result is None:
                    time.sleep(0.05)
                    continue
                pcm16, sr = result
                if self._engine == "openwakeword":
                    self.check_openwakeword(pcm16)
            except Exception:
                time.sleep(0.1)
