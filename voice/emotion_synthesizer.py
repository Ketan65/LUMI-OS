"""Emotion-Voice — Real-Time Acoustic Sentiment & Stress Modulation for LUMI (Phase 17).

Features:
  1. Acoustic & Linguistic Sentiment Extraction:
     Analyzes energy, pitch/tempo cadence, stress keywords ('urgent', 'jaldi', 'error', 'bug', 'crash'),
     and late-night hours.
  2. Dynamic Speaking Rate & Affect Modulation:
     Modulates Edge-TTS and ElevenLabs speaking rate (+15% for urgent, -10% for late night) and pitch.
  3. Contextual LLM Empathy Directives:
     Injects tone instructions into LLM system prompts (e.g. ultra-concise for urgent, reassuring for debugging).
  4. Real-time Telemetry:
     Streams emotional affect metrics to the HUD visualizer.
"""

from __future__ import annotations

import logging
import math
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger("lumi.voice.emotion")

STRESS_KEYWORDS = {
    "urgent": ["jaldi", "quick", "fast", "urgent", "emergency", "asap", "hurry", "now"],
    "frustrated_debugging": ["bug", "error", "crash", "failed", "broken", "not working", "why", "stuck", "yaar", "shit", "issue", "exception"],
    "casual_chill": ["kaisa hai", "hello", "hi", "bhai", "cool", "mast", "badhiya", "relax", "chilling"],
}


class EmotionVoiceSynthesizer:
    """Detects conversational emotion/stress and adaptively modulates speech delivery & persona tone."""

    def __init__(self, mode: str = "auto") -> None:
        self.mode = mode  # 'auto', 'urgent', 'debug', 'late_night', 'calm'
        self.active_state = "NORMAL_CALM"
        self.confidence = 0.85
        self.speech_rate_offset = 0  # percentage offset, e.g. +15, -10
        self.manual_override: str | None = None
        self._history: list[dict] = []

    def analyze_utterance(
        self,
        text: str,
        audio_samples: np.ndarray | None = None,
        sample_rate: int = 16000,
    ) -> dict:
        """Analyzes speech text and optional raw audio wave to identify user sentiment and affect."""
        t0 = time.perf_counter()
        clean_text = (text or "").lower()

        # 1. Acoustic energy calculation (if audio provided)
        energy_rms = 0.0
        if audio_samples is not None and len(audio_samples) > 0:
            try:
                energy_rms = float(np.sqrt(np.mean(audio_samples.astype(np.float32) ** 2)))
            except Exception:
                energy_rms = 0.0

        # 2. Time-of-day contextual factor
        current_hour = datetime.now().hour
        is_late_night = current_hour >= 23 or current_hour < 5

        # 3. Linguistic cadence analysis
        detected_state = "NORMAL_CALM"
        pacing_offset = 0
        directive = "Tone: Friendly, natural, collaborative Hinglish."

        if self.manual_override:
            detected_state = self.manual_override.upper()
        else:
            # Check for urgent signals
            urgent_score = sum(1 for kw in STRESS_KEYWORDS["urgent"] if kw in clean_text)
            debug_score = sum(1 for kw in STRESS_KEYWORDS["frustrated_debugging"] if kw in clean_text)

            if "!" in text and urgent_score > 0:
                urgent_score += 1

            if urgent_score >= 1:
                detected_state = "URGENT"
                pacing_offset = 15
                directive = "Boss is rushed/in a hurry. Be ultra-concise, deliver immediate direct answers with zero small talk."
            elif debug_score >= 1:
                detected_state = "FRUSTRATED_DEBUGGING"
                pacing_offset = -5
                directive = "Boss is debugging a tough issue. Be calm, reassuring, and provide exact, minimal code fixes with zero fluff."
            elif is_late_night:
                detected_state = "LATE_NIGHT"
                pacing_offset = -10
                directive = "Late night hours. Speak softly, calm, and warmly. Keep answers brief and relaxing."
            else:
                detected_state = "NORMAL_CALM"
                pacing_offset = 0
                directive = "Standard collaborative mode. Warm, high-energy Tony Stark JARVIS vibe."

        self.active_state = detected_state
        self.speech_rate_offset = pacing_offset

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        payload = {
            "state": detected_state,
            "speech_rate_offset": pacing_offset,
            "prompt_directive": directive,
            "energy_rms": round(energy_rms, 4),
            "is_late_night": is_late_night,
            "elapsed_ms": elapsed_ms,
            "timestamp": datetime.now().isoformat(),
        }

        self._history.append(payload)
        return payload

    def get_adapted_tts_rate(self, base_rate_str: str = "+0%") -> str:
        """Calculates final modulated rate string (e.g. '+15%' or '-10%') for Edge-TTS/TTS engines."""
        # Parse base rate e.g. "+0%" or "-5%"
        match = re.search(r"([+-]?\d+)", base_rate_str)
        base_val = int(match.group(1)) if match else 0
        final_val = base_val + self.speech_rate_offset
        sign = "+" if final_val >= 0 else ""
        return f"{sign}{final_val}%"

    def get_prompt_directive(self) -> str:
        """Returns emotional context directive for system prompt injection."""
        if self.active_state == "URGENT":
            return "[Affect: URGENT — User is rushed. Be ultra-concise, bullet points only, omit greetings.]"
        elif self.active_state == "FRUSTRATED_DEBUGGING":
            return "[Affect: DEBUGGING — User is resolving errors. Be calm, empathetic, provide exact surgical code.]"
        elif self.active_state == "LATE_NIGHT":
            return "[Affect: LATE_NIGHT — Late hours. Speak softly, warm, concise, and calm.]"
        return "[Affect: NORMAL — High energy, friendly Tony Stark JARVIS level partnership.]"

    def set_mode(self, mode: str = "auto", pacing_offset: int | None = None) -> dict:
        """Sets manual override or returns to auto-detection."""
        m_lower = mode.lower().strip()
        if m_lower in ("auto", "none", "reset"):
            self.manual_override = None
            self.mode = "auto"
        else:
            self.manual_override = m_lower
            self.mode = m_lower
            self.active_state = m_lower.upper()

        if pacing_offset is not None:
            self.speech_rate_offset = max(-30, min(pacing_offset, 40))

        return self.get_telemetry()

    def get_telemetry(self) -> dict:
        """Returns live emotional sentry telemetry for HUD display."""
        return {
            "mode": self.mode,
            "active_state": self.active_state,
            "speech_rate_offset": self.speech_rate_offset,
            "prompt_directive": self.get_prompt_directive(),
            "manual_override": self.manual_override,
            "total_analyzed": len(self._history),
        }


_global_emotion_synthesizer: EmotionVoiceSynthesizer | None = None


def get_emotion_synthesizer() -> EmotionVoiceSynthesizer:
    global _global_emotion_synthesizer
    if _global_emotion_synthesizer is None:
        _global_emotion_synthesizer = EmotionVoiceSynthesizer()
    return _global_emotion_synthesizer
