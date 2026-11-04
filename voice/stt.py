"""Speech-to-Text — faster-whisper (local, zero internet after model download).

Hindi + Hinglish ke liye 'small' model sweet spot hai.
Config: voice.stt { model, language, compute_type, device }
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel


class STT:
    def __init__(
        self,
        model: str = "small",
        language: str = "hi",          # Hindi priority; "auto" = detect
        compute_type: str = "int8",    # CPU friendly; "float16" if CUDA
        device: str = "auto",          # auto | cpu | cuda
    ):
        self.model_name = model
        self.language = language
        self.compute_type = compute_type
        self.device = device
        self._model: Optional[WhisperModel] = None

    def _load(self) -> WhisperModel:
        if self._model is None:
            dev = self.device
            if dev == "auto":
                dev = "cuda" if os.environ.get("CUDA_VISIBLE_DEVICES") else "cpu"
            print(f"[stt] Loading faster-whisper {self.model_name} on {dev} ({self.compute_type})")
            self._model = WhisperModel(
                self.model_name, device=dev, compute_type=self.compute_type
            )
        return self._model

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """numpy float32 audio (16 kHz mono) → Hindi/Hinglish text."""
        model = self._load()
        # faster-whisper expects 16 kHz mono float32
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        lang = None if self.language == "auto" else self.language
        segments, _info = model.transcribe(
            audio,
            language=lang,
            vad_filter=True,          # silence auto-chhod de
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        text = " ".join(seg.text for seg in segments).strip()
        return text

    def transcribe_file(self, path: str | Path) -> str:
        model = self._load()
        lang = None if self.language == "auto" else self.language
        segments, _info = model.transcribe(
            str(path), language=lang, vad_filter=True
        )
        return " ".join(seg.text for seg in segments).strip()


# ---- backward-compatible module-level API (used by telegram bridge tests) ----
_default_stt: Optional[STT] = None


def _get_default_stt() -> STT:
    global _default_stt
    if _default_stt is None:
        _default_stt = STT()
    return _default_stt


def transcribe(audio: np.ndarray, sample_rate: int = 16000) -> str:
    """Module-level convenience wrapper around STT.transcribe."""
    return _get_default_stt().transcribe(audio, sample_rate)

