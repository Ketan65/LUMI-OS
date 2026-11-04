"""LUMI — Personal AI Assistant (JARVIS style), sirf owner ke liye.

Full-duplex voice control pipeline:
    Wake word → VAD → STT → Intent Router → (System Control / Web Search / LLM)
        → TTS (Kokoro neural → pyttsx3) → Playback (sounddevice, barge-in)

Intent Router decide karta hai ki user kya chahta hai:
  - "open chrome", "notepad kholo" → system_control
  - "search web ..." → web_search
  - "mera naam kya hai", "yaad rakho ..." → personal identity / semantic vault
  - baki sab → LLM (qwen3:8b / hermes3) with JARVIS personality

Config: config.yaml + config/identity.json
"""

from __future__ import annotations

import json
import queue
import re
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import sounddevice as sd
import yaml

from .stt import STT
from .vad import SileroVAD
from .wake_word import WakeWordDetector
from .tts import synthesize, clean_for_speech
from brain.ollama_adapter import OllamaBrain

# JARVIS core modules
from core.personal_identity import load_identity, get_user_name, get_language, is_proactive
from core.system_control import (
    open_app, open_file, open_folder, run_shell, read_file, write_file,
    list_folder, system_info, get_clipboard, set_clipboard,
)
from core.jarvis_personality import build_system_prompt, tone_response
from core.proactive_assistant import ProactiveAssistant
from core.web_search import search_web, search_web_brief

# Optional semantic vault (personal memory)
try:
    from tools.vault import NeuralVault
    _VAULT_AVAILABLE = True
except Exception:
    _VAULT_AVAILABLE = False


def _load_cfg() -> dict:
    try:
        with open("config.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


class VoicePipeline:
    """
    LUMI Personal AI Assistant — JARVIS style.
    Instantiate once, call .start() / .stop().
    """

    SAMPLE_RATE = 16000
    CHANNELS = 1
    DTYPE = "int16"
    FRAME_MS = 30
    FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000  # 480

    def __init__(self, cfg: Optional[dict] = None):
        self.cfg = cfg or _load_cfg()

        # ---- Identity (JARVIS personal profile)
        self.identity = load_identity()
        self.user_name = get_user_name(self.identity)
        self.user_lang = get_language(self.identity)

        # ---- STT
        stt_cfg = self.cfg.get("voice", {}).get("stt", {})
        self.stt = STT(
            model=stt_cfg.get("model", "small"),
            language=stt_cfg.get("language", "hi"),
            compute_type=stt_cfg.get("compute_type", "int8"),
            device=stt_cfg.get("device", "auto"),
        )

        # ---- VAD
        self.vad = SileroVAD(threshold=float(self.cfg.get("voice", {}).get("vad_threshold", 0.5)))

        # ---- Wake word
        ww_cfg = self.cfg.get("voice", {}).get("wake_word", {})
        self.wake = WakeWordDetector(
            phrase=ww_cfg.get("phrase", "hey lumi"),
            threshold=float(ww_cfg.get("threshold", 0.5)),
            cooldown_s=float(ww_cfg.get("cooldown_s", 2.0)),
        )

        # ---- LLM (qwen3:8b resident via keep_alive=-1; hermes3 for agentic)
        llm_cfg = self.cfg.get("llm", {})
        self.brain = OllamaBrain(self.cfg)

        # ---- Semantic vault (personal memory)
        self.vault = None
        if _VAULT_AVAILABLE and self.cfg.get("vault", {}).get("semantic", False):
            try:
                self.vault = NeuralVault(semantic=True)
                print("[memory] Semantic vault loaded — personal memory active.")
            except Exception as exc:
                print(f"[memory] Vault init failed: {exc}")

        # ---- TTS playback state
        self._play_lock = threading.Lock()
        self._stop_play = threading.Event()
        self._play_thread: Optional[threading.Thread] = None
        self._is_speaking = False

        # ---- Audio I/O
        self._audio_q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=200)
        self._stream: Optional[sd.InputStream] = None

        # ---- Proactive assistant
        self.proactive = ProactiveAssistant(
            on_speak=self._proactive_speak,
            identity=self.identity,
            cfg=self.cfg,
        )

        # ---- Callbacks
        self.on_transcript: Optional[Callable[[str], None]] = None
        self.on_response: Optional[Callable[[str], None]] = None

        # ---- Wake word callback
        self.wake.on_detect(self._on_wake_word)

        self._listening = False
        self._listen_thread: Optional[threading.Thread] = None

        print(f"[lumi] Initialized for {self.user_name} ({self.user_lang})")

    # ----------------------------------------------------------- lifecycle

    def start(self) -> None:
        if self._listening:
            return
        self._listening = True
        self._stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=self.CHANNELS,
            dtype=self.DTYPE,
            blocksize=self.FRAME_SAMPLES,
            callback=self._audio_callback,
        )
        self._stream.start()
        self.wake.start(self._audio_provider)
        self.proactive.start()
        print(f"[voice] LUMI started. Say '{self.wake.phrase}' to activate. (JARVIS mode)")

    def stop(self) -> None:
        self._listening = False
        self._stop_play.set()
        self.proactive.stop()
        if self._stream:
            self._stream.close()
            self._stream = None
        self.wake.stop()
        if self._listen_thread:
            self._listen_thread.join(timeout=2.0)

    # ----------------------------------------------------------- audio IO

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            print(f"[audio] {status}")
        try:
            self._audio_q.put_nowait(indata.copy())
        except queue.Full:
            pass

    def _audio_provider(self):
        try:
            chunk = self._audio_q.get(timeout=0.1)
            return chunk, self.SAMPLE_RATE
        except queue.Empty:
            return None

    # ----------------------------------------------------------- wake word

    def _on_wake_word(self) -> None:
        print(f"[voice] Wake word detected — listening, {self.user_name}…")
        self._listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listen_thread.start()

    def _listen_loop(self) -> None:
        try:
            self._record_and_respond()
        finally:
            print(f"[voice] Back to wake-word listening, {self.user_name}.")

    def _record_and_respond(self) -> None:
        frames: list[np.ndarray] = []
        silent_frames = 0
        speech_started = False
        max_silent = int(1500 / self.FRAME_MS)
        max_frames = int(30_000 / self.FRAME_MS)

        while len(frames) < max_frames:
            try:
                chunk = self._audio_q.get(timeout=1.0)
            except queue.Empty:
                break

            pcm16 = chunk.flatten()
            pcm_f32 = pcm16.astype(np.float32) / 32768.0
            is_speech = self.vad.is_speech(pcm_f32)

            if is_speech:
                speech_started = True
                silent_frames = 0
                frames.append(pcm16)
            elif speech_started:
                silent_frames += 1
                frames.append(pcm16)
                if silent_frames >= max_silent:
                    break

        self.vad.reset()

        if not frames or not speech_started:
            print("[voice] No speech recorded.")
            return

        audio = np.concatenate(frames).astype(np.float32) / 32768.0
        self._respond(audio)

    # ----------------------------------------------------------- intent router

    def _respond(self, audio_f32: np.ndarray) -> None:
        self._stop_play.clear()

        # 1) STT
        try:
            text = self.stt.transcribe(audio_f32)
        except Exception as exc:
            print(f"[stt] Error: {exc}")
            return

        if not text.strip():
            print("[voice] Empty transcript.")
            return

        print(f"[you] {text}")
        if self.on_transcript:
            self.on_transcript(text)

        # 2) Intent routing
        intent = self._detect_intent(text)

        if intent["type"] == "system":
            reply = self._handle_system(intent, text)
        elif intent["type"] == "web":
            reply = self._handle_web(intent)
        elif intent["type"] == "memory":
            reply = self._handle_memory(intent, text)
        elif intent["type"] == "identity":
            reply = self._handle_identity(intent)
        else:
            reply = self._handle_llm(text)

        # 3) Tone + output
        reply = tone_response(reply, self.identity)
        print(f"[lumi] {reply}")
        if self.on_response:
            self.on_response(reply)

        clean = clean_for_speech(reply)
        if clean:
            self._speak(clean)

    def _detect_intent(self, text: str) -> dict:
        """Simple keyword-based intent router (reliable, no complex parsing)."""
        t = text.lower().strip()

        # System control
        system_keywords = ["open", "khol", "chala", "run", "start", "launch", "read file",
                           "padh", "likh", "write", "list", "folder", "system", "ram", "cpu",
                           "clipboard", "copy"]
        if any(k in t for k in system_keywords):
            return {"type": "system", "text": text}

        # Web search
        web_keywords = ["search", "search web", "google", "internet se", "kya hai", "kaun hai",
                        "kahan hai", "kab hai", "how to", "what is", "who is"]
        if any(k in t for k in web_keywords):
            return {"type": "web", "text": text}

        # Memory
        memory_keywords = ["yaad rakho", "remember", "meri yaad", "personal", "identity",
                           "mujhe yaad hai", "batao meri"]
        if any(k in t for k in memory_keywords):
            return {"type": "memory", "text": text}

        # Identity
        identity_keywords = ["mera naam", "who am i", "kaun ho tum", "tum kon ho",
                             "jarvis", "lumi", "assistant"]
        if any(k in t for k in identity_keywords):
            return {"type": "identity", "text": text}

        return {"type": "llm", "text": text}

    # ----------------------------------------------------------- handlers

    def _handle_system(self, intent: dict, text: str) -> str:
        t = text.lower()

        if any(k in t for k in ["open ", "khol ", "chala ", "start ", "launch "]):
            app = re.sub(r"(open|khol|chala|start|launch)\s+", "", t, count=1).strip()
            return open_app(app)

        if "read file" in t or "padh" in t:
            path = re.sub(r"(read file|padh)\s+", "", t, count=1).strip()
            return read_file(path)

        if "list folder" in t or "folder" in t:
            path = re.sub(r"(list folder|folder)\s+", "", t, count=1).strip() or "."
            return list_folder(path)

        if "system info" in t or "ram" in t or "cpu" in t:
            return system_info()

        if "clipboard" in t or "copy" in t:
            return get_clipboard()

        return open_app(t)

    def _handle_web(self, intent: dict) -> str:
        t = intent["text"]
        # Strip search keywords
        query = re.sub(r"(search|search web|google|internet se)\s*", "", t, count=1, flags=re.I).strip()
        if not query:
            query = t
        return search_web_brief(query)

    def _handle_memory(self, intent: dict, text: str) -> str:
        t = text.lower()
        if "yaad rakho" in t or "remember" in t:
            # Store in semantic vault + identity memory
            content = re.sub(r"(yaad rakho|remember)\s*", "", t, count=1).strip()
            if self.vault:
                try:
                    self.vault.add_text(
                        content,
                        source="personal_memory",
                        metadata={"type": "personal_memory", "user": self.user_name},
                    )
                    return f"Yaad rakh liya, {self.user_name}: {content}"
                except Exception as exc:
                    return f"Yaad rakhne mein dikkat: {exc}"
            identity = self.identity
            identity.setdefault("memory", {}).setdefault("notes", []).append(content)
            try:
                from core.personal_identity import save_identity
                save_identity(identity)
                return f"Yaad rakh liya, {self.user_name}: {content}"
            except Exception as exc:
                return f"Save error: {exc}"
        else:
            # Retrieve from vault
            query = re.sub(r"(meri yaad|mujhe yaad|personal|batao meri)\s*", "", t, count=1).strip()
            if self.vault:
                try:
                    results = self.vault.search(query, top_k=3)
                    if results:
                        snippets = [r.snippet for r in results[:2]]
                        return "Yaad hai mujhe: " + " | ".join(snippets)
                except Exception:
                    pass
            return f"{self.user_name}, meri yaad mein kuch specific nahi mila is baare mein."

    def _handle_identity(self, intent: dict) -> str:
        t = intent["text"].lower()
        if "mera naam" in t or "who am i" in t:
            return f"Aapka naam {self.user_name} hai, Sir. Main LUMI hoon, aapka personal AI assistant."
        if "kaun ho tum" in t or "tum kon ho" in t or "jarvis" in t or "lumi" in t:
            return f"Main LUMI hoon, {self.user_name} ka personal AI assistant — JARVIS style. Main aapke PC ko control kar sakta hoon, screen dekh sakta hoon, aur baat bhi kar sakta hoon."
        return f"Main LUMI hoon, aapka assistant, {self.user_name}."

    def _handle_llm(self, text: str) -> str:
        """LLM with JARVIS personality system prompt."""
        extra_context = ""
        if self.vault:
            extra_context = "\n\nYou have access to personal memory (semantic vault) — use it if relevant."

        system_prompt = build_system_prompt(self.identity, extra_context=extra_context)

        try:
            t0 = time.time()
            reply = self.brain.chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ])
            reply_text = getattr(reply, "text", None) or getattr(reply, "content", None) or str(reply)
            ms = int((time.time() - t0) * 1000)
            print(f"[llm] {ms}ms")
            return reply_text
        except Exception as exc:
            return f"Maaf kijiye {self.user_name}, dimaag mein thoda kharab hai: {exc}"

    # ----------------------------------------------------------- TTS / play

    def _speak(self, text: str) -> None:
        import tempfile
        from pathlib import Path as _Path

        tmp = _Path(tempfile.mkdtemp(prefix="lumi_tts_")) / "reply.wav"
        try:
            synthesize(text, tmp, engine="offline")
        except Exception as exc:
            print(f"[tts] Offline failed ({exc}) — trying auto")
            try:
                synthesize(text, tmp, engine="auto")
            except Exception as exc2:
                print(f"[tts] All engines failed: {exc2}")
                return

        self._play_file(tmp)

    def _play_file(self, path: _Path) -> None:
        import wave

        self._is_speaking = True
        try:
            with wave.open(str(path), "rb") as w:
                sr = w.getframerate()
                nch = w.getnchannels()
                sw = w.getsampwidth()
                frames = w.readframes(w.getnframes())

            if sw == 2:
                dtype = np.int16
            elif sw == 4:
                dtype = np.int32
            else:
                dtype = np.int16

            audio = np.frombuffer(frames, dtype=dtype)
            if nch > 1:
                audio = audio.reshape(-1, nch)

            chunk = self.FRAME_SAMPLES
            idx = 0
            while idx < len(audio) and self._listening and not self._stop_play.is_set():
                end = min(idx + chunk, len(audio))
                sd.play(audio[idx:end], samplerate=sr, blocking=True)
                idx = end

        except Exception as exc:
            print(f"[play] Error: {exc}")
        finally:
            self._is_speaking = False

    def _proactive_speak(self, text: str) -> None:
        """Proactive assistant calls this — speaks without wake word."""
        self._stop_play.clear()
        clean = clean_for_speech(text)
        if clean:
            self._speak(clean)

    # ----------------------------------------------------------- barge-in

    def interrupt(self) -> None:
        """Stop current TTS playback immediately."""
        self._stop_play.set()
        sd.stop()
        self._is_speaking = False


def run_cli() -> None:
    """Quick manual test of the voice pipeline (CLI mode)."""
    pipeline = VoicePipeline()
    pipeline.start()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print(f"\n[voice] Stopping…")
        pipeline.stop()


if __name__ == "__main__":
    run_cli()
