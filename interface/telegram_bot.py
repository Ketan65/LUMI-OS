"""Telegram bot interface — sync long-polling (requests), free tier only.
Same orchestrator.run_turn() as CLI+Web (Task H payoff): tools/memory/safety/
evolution sab LIVE. Security: ALLOWLIST mandatory — bina id ke msg = reject.
Token = ENV VAR TELEGRAM_BOT_TOKEN (config.yaml me KABHI nahi)."""

from __future__ import annotations

import os
import threading

import requests

API = "https://api.telegram.org/bot{token}/{method}"
MANUAL = """Telegram bot setup (USER STEPS):
  a) Telegram -> @BotFather -> /newbot -> naam do -> TOKEN copy
  b) setx TELEGRAM_BOT_TOKEN "123456:ABC..."  (naya terminal)
  c) Bot ko kuch bhejo -> bot apna chat_id batayega ->
     config.telegram.allowed_chat_ids mein add karo -> restart"""
HELP = ("LUMI Telegram — baaki sab same hai:\n"
        "/start  - help\n/status - provider/model/session\n"
        "/new    - fresh session\n/alerts - last 5 alerts\n"
        "/voice [on|off] - har reply ke saath audio note\n"
        "/decide <situation> - values pe faisla\n"
        "Baki text = normal chat (tools, memory, safety LIVE).")


def _chunks(text: str, n: int = 4096):
    """Reply >4096 = split (boundary pe) — no crash, Telegram limit safe."""
    while len(text) > n:
        cut = text.rfind("\n", 0, n)
        if cut < n // 2:
            cut = n
        yield text[:cut]
        text = text[cut:]
    if text:
        yield text


def send_text(token: str, chat_id: str, text: str, timeout: int = 10) -> bool:
    """Outbound send (bot reply + wire alerts) — fail = False, kabhi raise nahi."""
    try:
        for part in _chunks(text):
            r = requests.post(API.format(token=token, method="sendMessage"),
                              json={"chat_id": chat_id, "text": part},
                              timeout=timeout)
            if r.status_code != 200:
                return False
        return True
    except requests.RequestException:
        return False


def send_audio(token: str, chat_id: str, mp3: bytes, caption: str = "",
               timeout: int = 30) -> bool:
    """Voice OUT (Task T) — mp3 bytes audio note. fail = False, kabhi raise nahi."""
    try:
        r = requests.post(API.format(token=token, method="sendAudio"),
                          data={"chat_id": chat_id, "caption": caption[:500]},
                          files={"audio": ("reply.mp3", mp3, "audio/mpeg")},
                          timeout=timeout)
        return r.status_code == 200
    except requests.RequestException:
        return False


class TelegramBot:
    def __init__(self, orchestrator, allowed_ids, token: str | None = None,
                 poll_timeout: int = 50):
        self.orch = orchestrator
        self.token = (token if token is not None
                      else os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip()
        self.allowed = {str(x) for x in (allowed_ids or [])}
        self.poll_timeout = int(poll_timeout)
        self.offset = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # Voice mode per-chat (in-memory v1 — restart pe reset, DB = future)
        self.voice_mode: dict[str, bool] = {}

    @property
    def ready(self) -> bool:
        return bool(self.token)

    def _api(self, method: str, **payload) -> dict:
        r = requests.post(API.format(token=self.token, method=method),
                          json=payload, timeout=self.poll_timeout + 10)
        r.raise_for_status()
        return r.json()

    def _send(self, chat_id: str, text: str) -> None:
        send_text(self.token, chat_id, text, timeout=15)

    def handle_update(self, upd: dict) -> None:
        """Ek update ka poora flow — unit tests yahan direct call karte hain."""
        msg = upd.get("message") or {}
        chat_id = str((msg.get("chat") or {}).get("id") or "")
        text = (msg.get("text") or "").strip()
        has_media = bool(msg.get("voice") or msg.get("audio"))
        if not chat_id or (not text and not has_media):
            return
        if chat_id not in self.allowed:
            print(f"[telegram] WARN unauthorized chat_id={chat_id}")
            self._send(chat_id, "Unauthorized. Tumhara chat_id: "
                       f"{chat_id} — isse config telegram.allowed_chat_ids "
                       "mein add karo")
            return
        if has_media:
            self._voice(msg, chat_id)        # Task S: voice note -> STT -> chat
            return
        if text.startswith("/"):
            self._send(chat_id, self._command(text, chat_id))
            return
        try:
            try:                              # feel: bot "typing" dikhaye
                self._api("sendChatAction", chat_id=chat_id, action="typing")
            except Exception:                  # noqa: BLE001 — feel optional
                pass
            turn = self.orch.run_turn(text)    # SAME engine — sab LIVE
            reply = turn.get("reply") or "(khaali reply)"
            self._send(chat_id, reply)
            self._maybe_voice(chat_id, reply)
            self.orch.maybe_reflect(text, turn.get("reply") or "")
        except Exception as exc:              # noqa: BLE001 — friendly, no stack
            print(f"[telegram] turn error: {exc}")
            try:
                self._send(chat_id, "Kuch gadbad ho gayi — dobara try karo.")
            except Exception:                  # noqa: BLE001
                pass

    def _voice(self, msg: dict, chat_id: str) -> None:
        """Voice note -> local whisper transcript -> 🎙 line -> SAME run_turn -> voice note reply."""
        import os
        import tempfile
        from pathlib import Path
        from voice import stt
        vc = getattr(self.orch, "config", {}).get("voice") or {}
        if not vc.get("enabled"):
            self._send(chat_id, "Voice band hai (config) — text likh do.")
            return
        meta = msg.get("voice") or msg.get("audio") or {}
        path = ""
        try:
            path = self._download(str(meta.get("file_id") or ""))
            text = stt.transcribe(
                path,
                model=str(vc.get("whisper_model", "small")),
                language=str(vc.get("language", "auto")),
                device=str(vc.get("device", "auto")),
                initial_prompt="LUMI, Jarvis. Hindi Hinglish: LUMI kya haal hai, open notepad, system status batao.",
            )
        except Exception as exc:            # noqa: BLE001 — friendly, no stack
            print(f"[telegram] voice error: {exc}")
            text = ""
        finally:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass
        if not text:
            self._send(chat_id, "Samajh nahi aaya, kripya text likh do.")
            return
        try:
            turn = self.orch.run_turn(text)
            reply = turn.get("reply") or ""
            self._send(chat_id, f"🎙 {text}\n\n{reply}")
            # Two-way voice bridge: voice in gets voice out!
            self._send_voice_audio(chat_id, reply)
            self.orch.maybe_reflect(text, turn.get("reply") or "")
        except Exception as exc:            # noqa: BLE001
            print(f"[telegram] turn error: {exc}")
            self._send(chat_id, "Kuch gadbad ho gayi — dobara try karo.")

    def _download(self, file_id: str) -> str:
        """Telegram file -> local temp (caller delete karega)."""
        import tempfile
        from pathlib import Path
        info = self._api("getFile", file_id=file_id)
        rel = (info.get("result") or {}).get("file_path") or ""
        r = requests.get(f"https://api.telegram.org/file/bot{self.token}/{rel}", timeout=30)
        r.raise_for_status()
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(rel).suffix or ".oga") as tf:
            tf.write(r.content)
            return tf.name

    def _send_voice_audio(self, chat_id: str, reply: str) -> None:
        """Synthesize and send mp3 voice note to telegram chat."""
        import tempfile
        tc = (getattr(self.orch, "config", {}).get("voice") or {}).get("tts") or {}
        if not tc.get("enabled", True):
            return
        from voice import tts
        tmp = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tf:
                tmp = tf.name
            tts.synthesize(
                reply,
                tmp,
                voice=str(tc.get("voice", "hi-IN-MadhurNeural")),
                engine=str(tc.get("engine", "auto")),
                rate=str(tc.get("rate", "+0%")),
            )
            with open(tmp, "rb") as fh:
                send_audio(self.token, chat_id, fh.read(), caption=reply[:300])
        except Exception as exc:
            print(f"[telegram] voice-out error: {exc}")
        finally:
            if tmp:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    def _maybe_voice(self, chat_id: str, reply: str) -> None:
        """Voice mode ON -> reply ka mp3 audio note (text pehle ja chuka ✅)."""
        if not self.voice_mode.get(chat_id):
            return
        self._send_voice_audio(chat_id, reply)

    def _command(self, text: str, chat_id: str = "") -> str:
        name = text.split()[0].lower()
        if name == "/start":
            return HELP
        if name == "/status":
            b = self.orch.brain
            return ("LUMI status — provider: "
                    f"{getattr(b, 'last_provider', '-')} | model: "
                    f"{getattr(b, 'last_model', getattr(b, 'model', '-'))} | "
                    f"session: {self.orch._sid()}")
        if name in {"/new", "/alerts", "/decide", "/briefing", "/plan", "/tools", "/facts"}:
            _, out = self.orch.command(text)
            return out
        if name == "/voice":                  # per-chat voice mode (Task T)
            parts = text.split()
            if len(parts) == 1:
                on = self.voice_mode.get(chat_id, False)
                return f"Voice mode: {'ON' if on else 'OFF'} — /voice on|off"
            if parts[1].lower() in ("on", "off"):
                self.voice_mode[chat_id] = parts[1].lower() == "on"
                return (f"Voice mode {parts[1].lower().upper()} — har reply "
                        "ke saath audio note aayega (text pehle jaisa)."
                        if self.voice_mode[chat_id]
                        else "Voice mode OFF — sirf text (jaise pehle).")
            return "Usage: /voice on | /voice off | /voice"
        return "Command nahi samjha — /start /status /new /alerts /briefing /plan /voice ya plain text."

    # -- daemon thread (long-poll) ---------------------------------------
    def poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                data = self._api("getUpdates", offset=self.offset,
                                 timeout=self.poll_timeout)
            except Exception as exc:          # noqa: BLE001 — network fail = retry
                if not self._stop.is_set():
                    print(f"[telegram] poll error: {exc} (retry in 5s)")
                    self._stop.wait(5)
                continue
            for upd in (data.get("result") or []):
                self.offset = int(upd.get("update_id", 0)) + 1
                try:
                    self.handle_update(upd)
                except Exception as exc:      # noqa: BLE001 — one bad msg = isolate
                    print(f"[telegram] update error: {exc}")

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self.poll_loop, daemon=True,
                                        name="lumi-telegram")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=60)     # long-poll max 50s + buffer
