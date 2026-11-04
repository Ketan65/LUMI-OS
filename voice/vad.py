"""Voice Activity Detection — Silero VAD ONNX with energy-based fallback.

16 kHz mono audio chunks process karta hai aur speech probability return karta hai.
Tries Silero VAD ONNX from multiple mirrors; falls back to simple RMS energy VAD
if all downloads fail (works offline, zero dependencies).
"""

from __future__ import annotations

import math
import urllib.request
from pathlib import Path
from typing import Optional

import numpy as np
import onnxruntime as rt

_MODEL_URLS = [
    "https://huggingface.co/snakers4/silero-vad/resolve/main/files/silero_vad.onnx",
    "https://github.com/snakers4/silero-vad/raw/master/files/silero_vad.onnx",
]
_SAMPLE_RATE = 16000
_WINDOW_SIZE = 512  # 32 ms at 16 kHz


class SileroVAD:
    """
    VAD detector. Uses Silero VAD ONNX if model downloads successfully;
    otherwise falls back to RMS energy-based VAD (always works offline).
    """

    def __init__(
        self,
        model_path: str | Path | None = None,
        threshold: float = 0.5,
        sample_rate: int = _SAMPLE_RATE,
    ):
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.model_path = Path(
            model_path or Path.home() / ".cache" / "lumi" / "silero_vad.onnx"
        )
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        self._use_silero = False
        self.sess = None
        self._h = None
        self._c = None
        self._try_load_silero()
        # Energy fallback stats
        self._energy_history: list[float] = []
        self._noise_floor: Optional[float] = None

    def _try_load_silero(self) -> None:
        for url in _MODEL_URLS:
            try:
                if not self.model_path.is_file():
                    print(f"[vad] Downloading Silero VAD model to {self.model_path}")
                    urllib.request.urlretrieve(url, str(self.model_path))
                    print("[vad] Model download complete")
                self.sess = rt.InferenceSession(str(self.model_path))
                self._use_silero = True
                self._reset_state()
                print("[vad] Silero VAD ONNX loaded")
                return
            except Exception as exc:
                print(f"[vad] Mirror failed ({url}): {exc}")
                continue
        print("[vad] All Silero mirrors failed - using energy-based VAD fallback")

    def _reset_state(self) -> None:
        if self._use_silero:
            self._h = np.zeros((2, 1, 128), dtype=np.float32)
            self._c = np.zeros((2, 1, 128), dtype=np.float32)

    # -- energy fallback ---------------------------------------------------

    def _rms(self, chunk: np.ndarray) -> float:
        if len(chunk) == 0:
            return 0.0
        return float(np.sqrt(np.mean(chunk ** 2)))

    def _energy_is_speech(self, chunk: np.ndarray) -> bool:
        rms = self._rms(chunk)
        self._energy_history.append(rms)
        if len(self._energy_history) > 100:
            self._energy_history.pop(0)
        # Noise floor = 20th percentile of recent energy
        if len(self._energy_history) >= 10:
            sorted_e = sorted(self._energy_history)
            self._noise_floor = sorted_e[max(0, len(sorted_e) // 5)]
        if self._noise_floor is None or self._noise_floor <= 0:
            return rms > 0.02
        return rms > max(self._noise_floor * 4.0, 0.02)

    # -- public API --------------------------------------------------------

    def is_speech(self, chunk: np.ndarray) -> bool:
        """chunk: 1-D float32 numpy array, 16 kHz mono."""
        if chunk.dtype != np.float32:
            chunk = chunk.astype(np.float32)
        if len(chunk) < _WINDOW_SIZE:
            chunk = np.pad(chunk, (0, _WINDOW_SIZE - len(chunk)))
        chunk = chunk[:_WINDOW_SIZE]

        if self._use_silero and self.sess is not None:
            input_dict = {
                "input": chunk.reshape(1, len(chunk)),
                "h": self._h,
                "c": self._c,
                "sr": np.array(self.sample_rate, dtype=np.int64),
            }
            out, (h, c) = self.sess.run(None, input_dict)
            self._h, self._c = h, c
            return bool(out[0][0] > self.threshold)
        return self._energy_is_speech(chunk)

    def reset(self) -> None:
        """Nayi utterance shuru hone pe call karein."""
        if self._use_silero:
            self._reset_state()
        else:
            self._energy_history = []
            self._noise_floor = None
