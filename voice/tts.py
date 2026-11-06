"""Voice OUT — ElevenLabs + Edge-TTS + offline Kokoro neural + pyttsx3 classic.

Supports:
  - ElevenLabs Multilingual V2 (Adam / Rachel / Charlie / etc.) for ultra-realistic speech
  - Online high quality neural voices via edge-tts (Madhur / Swara / Neerja / Prabhat)
  - Offline NEURAL fallback via Kokoro-82M (kokoro-onnx, local CPU — bina internet
    natural awaaz; Devanagari text → Hindi voice, Latin → English voice)
  - Offline classic fallback via pyttsx3 (jab neural files na hon / download pending).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

_LOG = Path("data/logs/brain.log")

VOICE_PROFILES: dict[str, str] = {
    # Edge-TTS Natural Indian & Hinglish Voices (Free, Zero Latency)
    "hinglish_male": "hi-IN-MadhurNeural",
    "hinglish_female": "hi-IN-SwaraNeural",
    "indian_english_female": "en-IN-NeerjaNeural",
    "indian_english_male": "en-IN-PrabhatNeural",
    "english_andrew": "en-US-AndrewNeural",

    # ElevenLabs Multilingual V2 IDs
    "eleven_adam": "pNInz6obpgDQGcFmaJgB",
    "eleven_rachel": "21m00Tcm4TlvDq8ikWAM",
    "eleven_charlie": "IKne3meq5aSn9XLyUdCD",
    "eleven_antoni": "ErXwobaYiN019PkySvjV",
    "eleven_bella": "EXAVITQu4vr4xnSDxMaL",
    "eleven_george": "JBFqnCBsd6RMkjVDRZzb",
}


def _log(msg: str) -> None:
    try:
        with _LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} tts {msg}\n")
    except OSError:
        pass


def _is_emoji(ch: str) -> bool:
    o = ord(ch)
    return (0x1F000 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF
            or 0x2190 <= o <= 0x21FF or o == 0xFE0F or 0x2B00 <= o <= 0x2BFF)


def clean_for_speech(text: str, limit: int = 2000) -> str:
    """Markdown/emoji/URL hatao — speech me '*' ya 'bullet' na sunai de."""
    t = str(text or "")
    t = re.sub(r"```.*?```", " (code chhoda gaya) ", t, flags=re.S)
    t = re.sub(r"`([^`\n]+)`", r"\1", t)
    t = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", t)
    t = re.sub(r"(?<![\w])\*([^*\n]+)\*(?![\w])", r"\1", t)
    t = re.sub(r"https?://\S+", "link", t)
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"^\s*[-*•]\s+", ", ", t, flags=re.M)
    t = "".join(ch for ch in t if ch in "\n\t" or not _is_emoji(ch))
    t = re.sub(r"[ \t]+", " ", t).strip()
    if len(t) > limit:
        suffix = " (aur bahut lamba jawab...)"
        t = t[:max(0, limit - len(suffix))].rsplit(" ", 1)[0] + suffix
    return t


def synthesize_offline(clean_text: str, out_path: str | Path) -> str:
    """Local offline synthesis using pyttsx3."""
    import pyttsx3
    engine = pyttsx3.init()
    engine.save_to_file(clean_text, str(out_path))
    engine.runAndWait()
    return str(out_path)


# ---- offline NEURAL tier (Kokoro-82M / kokoro-onnx, local CPU) ----------------

_TTS_CFG: dict | None = None
_KOKORO = None
_KOKORO_ERR: str | None = None


def _tts_cfg() -> dict:
    """config.yaml voice.tts block (lazy, cached) — offline neural settings."""
    global _TTS_CFG
    if _TTS_CFG is None:
        out: dict = {}
        try:
            import yaml
            with open("config.yaml", "r", encoding="utf-8") as f:
                voice_blk = (yaml.safe_load(f) or {}).get("voice") or {}
                out = voice_blk.get("tts") or {}
        except Exception:
            out = {}
        _TTS_CFG = out
    return _TTS_CFG


def _kokoro_paths() -> tuple[Path, Path]:
    cfg = _tts_cfg()
    base = Path.home() / ".cache" / "kokoro-onnx"
    model_raw = cfg.get("kokoro_model") or base / "kokoro-v1.1-zh.int8.onnx"
    voices_raw = cfg.get("kokoro_voices") or base / "voices-v1.1-zh.bin"
    model = Path(model_raw).expanduser().resolve()
    voices = Path(voices_raw).expanduser().resolve()
    return model, voices


def _get_kokoro():
    """Lazy singleton — pehli call pe ONNX session load, phir reuse (har call fast)."""
    global _KOKORO, _KOKORO_ERR
    if _KOKORO is not None:
        return _KOKORO
    if _KOKORO_ERR:
        raise RuntimeError(_KOKORO_ERR)
    model, voices = _kokoro_paths()
    if not (model.is_file() and voices.is_file()):
        _KOKORO_ERR = f"kokoro_files_missing: {model}"
        raise RuntimeError(_KOKORO_ERR)
    try:
        from kokoro_onnx import Kokoro
        _KOKORO = Kokoro(str(model), str(voices))
    except Exception as exc:
        _KOKORO_ERR = f"kokoro_init_failed: {exc}"
        raise RuntimeError(_KOKORO_ERR) from exc
    return _KOKORO


def _is_devanagari(text: str) -> bool:
    return any("\u0900" <= ch <= "\u097f" for ch in text)


def _pick_kokoro_voice(engine, text: str) -> str:
    """Devanagari → Hindi voice (file me ho to), warna configured/default Latin voice."""
    cfg = _tts_cfg()
    available = set(engine.get_voices())
    if not available:
        raise RuntimeError("kokoro_empty_voice_list")
    if _is_devanagari(text):
        for cand in (cfg.get("kokoro_hindi_voice"), "female_pravda", "hf_alpha", "hf_beta"):
            if cand and cand != "auto" and cand in available:
                return str(cand)
        # Hindi voice is pack me nahi (v1.1-zh = en+zh only) — model Hindi jaanta
        # nahi, garbled awaaz se better hai chain ko pyttsx3 pe girna (purana behavior)
        raise RuntimeError("kokoro_no_hindi_voice")
    default = cfg.get("kokoro_voice") or "af_sol"
    if default != "auto" and default in available:
        return str(default)
    for cand in ("af_sol", "af_maple", "bf_vale", "af_heart", "af_bella", "af_sky"):
        if cand in available:
            return cand
    return sorted(available)[0]


def _write_wav(path: str | Path, audio, sample_rate: int) -> None:
    """numpy float audio → mono 16-bit WAV (stdlib wave — koi extra dep nahi)."""
    import wave
    import numpy as np
    a = np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0)
    pcm = (a * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes(pcm.tobytes())


def synthesize_kokoro(clean_text: str, out_path: str | Path) -> str:
    """Offline NEURAL synthesis — Kokoro-82M on local CPU, zero internet.

    Voice pick: Devanagari text → Hindi voice (female_pravda/hf_*), Latin → af_heart.
    Fail hoti hai to chain caller pyttsx3 pe girati hai (graceful).
    """
    cfg = _tts_cfg()
    k = _get_kokoro()
    voice = _pick_kokoro_voice(k, clean_text)
    lang = "hi" if _is_devanagari(clean_text) else "en-us"
    speed = float(cfg.get("kokoro_speed") or 1.0)
    t0 = time.time()
    audio, sr = k.create(clean_text, voice, speed=speed, lang=lang)
    if audio is None or len(audio) == 0:
        raise RuntimeError("kokoro_empty_audio")
    _write_wav(out_path, audio, sr)
    ms = int((time.time() - t0) * 1000)
    _log(f"synth kokoro ok voice={voice} lang={lang} ms={ms} chars={len(clean_text)}")
    print(f"[tts] kokoro neural synthesized {len(clean_text)} chars in {ms}ms ({voice}/{lang})")
    return str(out_path)


def _synthesize_offline_chain(clean_text: str, out_path, t0: float) -> str:
    """Offline chain: Kokoro neural (agar files hon) → pyttsx3 classic.

    Dono fail → RuntimeError('offline_tts_error: ...') (purana error shape preserve).
    """
    neural_exc: Exception | None = None
    if str(_tts_cfg().get("offline_engine", "neural")).lower() != "classic":
        try:
            res = synthesize_kokoro(clean_text, out_path)
            ms = int((time.time() - t0) * 1000)
            _log(f"synth offline neural ok ms={ms} chars={len(clean_text)}")
            return res
        except Exception as exc:
            neural_exc = exc
            print(f"[tts] kokoro neural unavailable ({exc}) — falling back to pyttsx3")
            _log(f"kokoro_failed err={exc}")
    try:
        res = synthesize_offline(clean_text, out_path)
        ms = int((time.time() - t0) * 1000)
        _log(f"synth offline classic ok ms={ms} chars={len(clean_text)}")
        return res
    except Exception as exc:
        if neural_exc is not None:
            raise RuntimeError(f"offline_tts_error: neural={neural_exc}; classic={exc}") from exc
        raise RuntimeError(f"offline_tts_error: {exc}") from exc


def synthesize_elevenlabs(clean_text: str, out_path: str | Path,
                          voice_id: str = "pNInz6obpgDQGcFmaJgB",
                          api_key: str | None = None,
                          model_id: str = "eleven_multilingual_v2") -> str:
    key = api_key or os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVEN_API_KEY")
    if not key:
        raise ValueError("missing_elevenlabs_api_key")

    resolved_id = VOICE_PROFILES.get(voice_id, voice_id)
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{resolved_id}"
    headers = {
        "xi-api-key": key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": clean_text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.8,
            "style": 0.0,
            "use_speaker_boost": True,
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = resp.read()
            Path(out_path).write_bytes(data)
            ms = int((time.time() - t0) * 1000)
            _log(f"synth elevenlabs ok voice={resolved_id} ms={ms} chars={len(clean_text)}")
            print(f"[tts] elevenlabs synthesized {len(clean_text)} chars in {ms}ms ({resolved_id})")
            return str(out_path)
    except urllib.error.HTTPError as exc:
        err_msg = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"elevenlabs_http_{exc.code}: {err_msg}") from exc
    except Exception as exc:
        raise RuntimeError(f"elevenlabs_error: {exc}") from exc


def synthesize(text: str, out_path, voice: str = "hi-IN-MadhurNeural",
               rate: str = "+0%", engine: str = "auto",
               offline_fallback: bool = True,
               api_key: str | None = None) -> str:
    """text -> audio file.

    Priority:
    1. If engine == 'offline' -> offline chain: Kokoro neural (local, zero internet)
       -> pyttsx3 classic (jab neural files missing hon).
    2. If engine == 'elevenlabs' or (engine == 'auto' and ElevenLabs key is present or voice starts with 'eleven_'):
       attempts ElevenLabs Multilingual V2.
    3. Edge-TTS neural voice (hi-IN-MadhurNeural or hi-IN-SwaraNeural for natural Hinglish).
    4. Offline chain fallback if network is down (Kokoro neural -> pyttsx3).
    """
    clean = clean_for_speech(text)
    if not clean:
        raise ValueError("empty_after_clean")

    # Resolve alias to full voice identifier
    resolved_voice = VOICE_PROFILES.get(voice, voice)
    t0 = time.time()

    if engine == "offline":
        # offline chain khud error shape rakhta hai: offline_tts_error: ...
        return _synthesize_offline_chain(clean, out_path, t0)

    # ElevenLabs check
    eleven_key = api_key or os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVEN_API_KEY")
    is_eleven_voice = voice.startswith("eleven_") or voice in {
        "pNInz6obpgDQGcFmaJgB", "21m00Tcm4TlvDq8ikWAM", "IKne3meq5aSn9XLyUdCD",
        "ErXwobaYiN019PkySvjV", "EXAVITQu4vr4xnSDxMaL", "JBFqnCBsd6RMkjVDRZzb"
    }

    if (engine == "elevenlabs" or (engine == "auto" and (eleven_key or is_eleven_voice))) and eleven_key:
        try:
            res = synthesize_elevenlabs(clean, out_path, voice_id=resolved_voice, api_key=eleven_key)
            return res
        except Exception as exc:
            print(f"[tts] ElevenLabs unavailable ({exc}) — falling back to Edge-TTS")
            _log(f"elevenlabs_failed voice={resolved_voice} err={exc}")
            if engine == "elevenlabs" and not offline_fallback:
                raise

    # If an ElevenLabs voice was selected but ElevenLabs key is absent or failed,
    # map to appropriate natural Hinglish Edge voice so speech never fails
    edge_voice = resolved_voice
    if is_eleven_voice or edge_voice.startswith("eleven_"):
        edge_voice = "hi-IN-MadhurNeural" if "adam" in voice or "charlie" in voice else "hi-IN-SwaraNeural"

    # Edge-TTS
    try:
        import edge_tts

        async def _run() -> None:
            await edge_tts.Communicate(clean, edge_voice, rate=rate).save(str(out_path))

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_run())
            ms = int((time.time() - t0) * 1000)
            _log(f"synth edge ok voice={edge_voice} ms={ms} chars={len(clean)}")
            print(f"[tts] edge-tts synthesized {len(clean)} chars in {ms}ms ({edge_voice})")
            return str(out_path)
        finally:
            loop.close()
    except Exception as exc:
        if offline_fallback:
            print(f"[tts] edge-tts unavailable ({exc}) — offline fallback engaged (Kokoro -> pyttsx3)")
            try:
                return _synthesize_offline_chain(clean, out_path, t0)
            except Exception as offline_exc:
                _log(f"all_tts_failed voice={edge_voice} err={offline_exc}")
                raise RuntimeError(f"engine_unavailable: {exc}") from exc
        _log(f"engine_unavailable voice={edge_voice} err={type(exc).__name__}")
        raise RuntimeError(f"engine_unavailable: {exc}") from exc
