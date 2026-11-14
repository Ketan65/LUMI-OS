"""Speech-to-Text — faster-whisper with CUDA acceleration on NVIDIA RTX GPUs.

Hindi + Hinglish ke liye 'small' model sweet spot hai.
Config: voice.stt { model, language, compute_type, device }
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np

_CUDA_DLLS_CONFIGURED = False


def _setup_cuda_dlls() -> None:
    """Ensure Windows dynamic loader can find cublas64_12.dll and cudnn from torch/nvidia packages."""
    global _CUDA_DLLS_CONFIGURED
    if _CUDA_DLLS_CONFIGURED or os.name != "nt":
        return
    _CUDA_DLLS_CONFIGURED = True
    candidate_dirs: list[Path] = []
    # 1. From torch
    try:
        import torch
        candidate_dirs.append(Path(torch.__file__).parent / "lib")
    except Exception:
        pass
    # 2. From nvidia cublas / cudnn in site-packages
    try:
        import site
        sp_dirs = site.getsitepackages() if hasattr(site, "getsitepackages") else []
        for sp in sp_dirs:
            p = Path(sp)
            candidate_dirs.append(p / "nvidia" / "cublas" / "bin")
            candidate_dirs.append(p / "nvidia" / "cudnn" / "bin")
    except Exception:
        pass

    for d in candidate_dirs:
        if d.is_dir():
            try:
                os.add_dll_directory(str(d))
            except Exception:
                pass
            os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")


class STT:
    def __init__(
        self,
        model: str = "small",
        language: str = "hi",          # Hindi priority; "auto" = detect
        compute_type: str = "float16", # CUDA float16; auto-falls back to int8 if CPU
        device: str = "cuda",          # cuda | auto | cpu
    ):
        self.model_name = model
        self.language = language
        self.compute_type = compute_type
        self.device = device
        self._model: Optional[Any] = None

    def _load(self) -> Any:
        if self._model is not None:
            return self._model

        _setup_cuda_dlls()
        from faster_whisper import WhisperModel
        target_dev = self.device
        target_compute = self.compute_type

        # Check torch CUDA availability if target is cuda or auto
        if target_dev in ("auto", "cuda"):
            has_cuda = False
            try:
                import torch
                has_cuda = torch.cuda.is_available()
            except Exception:
                pass

            if has_cuda:
                try:
                    t0 = time.time()
                    print(f"[stt] Loading faster-whisper {self.model_name} on CUDA ({target_compute})...")
                    self._model = WhisperModel(
                        self.model_name, device="cuda", compute_type=target_compute
                    )
                    self.device = "cuda"
                    self.compute_type = target_compute
                    ms = int((time.time() - t0) * 1000)
                    print(f"[stt] faster-whisper {self.model_name} running on CUDA float16 ({ms}ms load, RTX GPU accelerated).")
                    return self._model
                except Exception as exc:
                    print(f"[stt] CUDA init failed ({exc}) — falling back to CPU int8")

        # CPU Fallback
        t0 = time.time()
        print(f"[stt] Loading faster-whisper {self.model_name} on CPU (int8)...")
        self._model = WhisperModel(
            self.model_name, device="cpu", compute_type="int8"
        )
        self.device = "cpu"
        self.compute_type = "int8"
        ms = int((time.time() - t0) * 1000)
        print(f"[stt] faster-whisper loaded on CPU ({ms}ms).")
        return self._model

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """numpy float32 audio (16 kHz mono) → Hindi/Hinglish text."""
        model = self._load()
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        lang = None if self.language == "auto" else self.language
        t0 = time.time()
        segments, _info = model.transcribe(
            audio,
            language=lang,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=400),
            beam_size=1,
            temperature=0.0,
        )
        text = " ".join(seg.text for seg in segments).strip()
        ms = int((time.time() - t0) * 1000)
        safe_preview = text[:50].encode("ascii", errors="replace").decode("ascii")
        print(f"[stt] Transcribed in {ms}ms ({self.device}/{self.compute_type}): {safe_preview}")
        return text

    def transcribe_file(self, path: str | Path) -> str:
        model = self._load()
        lang = None if self.language == "auto" else self.language
        t0 = time.time()
        segments, _info = model.transcribe(
            str(path),
            language=lang,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=400),
            beam_size=1,
            temperature=0.0,
        )
        text = " ".join(seg.text for seg in segments).strip()
        ms = int((time.time() - t0) * 1000)
        safe_preview = text[:50].encode("ascii", errors="replace").decode("ascii")
        print(f"[stt] Transcribed file in {ms}ms ({self.device}/{self.compute_type}): {safe_preview}")
        return text


# ---- backward-compatible module-level API (used by telegram bridge tests) ----
_default_stt: Optional[STT] = None


def _get_default_stt() -> STT:
    global _default_stt
    if _default_stt is None:
        _default_stt = STT()
    return _default_stt


def transcribe(
    audio: np.ndarray | str | Path,
    sample_rate: int = 16000,
    model: str = "small",
    language: str = "auto",
    device: str = "auto",
    initial_prompt: Optional[str] = None,
) -> str:
    """Module-level convenience wrapper around STT.transcribe and STT.transcribe_file."""
    stt_inst = _get_default_stt()
    if model and stt_inst.model_name != model:
        stt_inst.model_name = model
    if language and stt_inst.language != language:
        stt_inst.language = language
    if isinstance(audio, (str, Path)):
        return stt_inst.transcribe_file(audio)
    return stt_inst.transcribe(audio, sample_rate)

