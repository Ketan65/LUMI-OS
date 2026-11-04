"""Emotion-Voice Tools for LUMI (Phase 17).

Provides LLM-callable tools for:
  - detect_voice_affect: analyzes speech cadence and sentiment to adapt tone
  - configure_vocal_affect: overrides or configures emotional affect and speech pacing
  - get_vocal_affect_status: retrieves emotional telemetry for HUD display
"""

from __future__ import annotations

import logging
from typing import Any

from tools.registry import Tool, ToolRegistry
from voice.emotion_synthesizer import EmotionVoiceSynthesizer, get_emotion_synthesizer

logger = logging.getLogger("lumi.tools.emotion_voice")


def register_emotion_voice_tools(
    registry: ToolRegistry,
    emotion_synth: EmotionVoiceSynthesizer | None = None,
) -> EmotionVoiceSynthesizer:
    """Registers acoustic affect and emotional voice modulation tools into ToolRegistry."""
    active_synth = emotion_synth or get_emotion_synthesizer()

    def detect_voice_affect(utterance_text: str) -> dict:
        """Analyzes speech utterance to detect urgency, debugging frustration, or casual calm, dynamically tuning voice pacing."""
        return active_synth.analyze_utterance(text=utterance_text)

    def configure_vocal_affect(mode: str = "auto", pacing_offset: int = 0) -> dict:
        """Configures vocal empathy mode ('auto', 'urgent', 'debug', 'late_night', 'calm') and manual pacing offset."""
        return active_synth.set_mode(mode=mode, pacing_offset=pacing_offset)

    def get_vocal_affect_status() -> dict:
        """Returns the current emotional affect state, active speech rate offset, and prompt directive."""
        return active_synth.get_telemetry()

    # Register in ToolRegistry
    registry.register(Tool(
        name="detect_voice_affect",
        description="Analyzes speech cadence and emotional stress (urgency, debugging frustration, casual calm) to tune voice speed and empathy.",
        params_schema={
            "type": "object",
            "properties": {
                "utterance_text": {"type": "string", "description": "The user's spoken or typed prompt text"},
            },
            "required": ["utterance_text"],
        },
        handler=detect_voice_affect,
        risk="auto",
    ))

    registry.register(Tool(
        name="configure_vocal_affect",
        description="Configures emotional voice affect mode ('auto', 'urgent', 'debug', 'late_night', 'calm') and speech rate modulation.",
        params_schema={
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["auto", "urgent", "debug", "late_night", "calm"], "default": "auto"},
                "pacing_offset": {"type": "integer", "default": 0, "description": "Percentage speech rate adjustment (e.g. +15 or -10)"},
            },
        },
        handler=configure_vocal_affect,
        risk="auto",
    ))

    registry.register(Tool(
        name="get_vocal_affect_status",
        description="Returns current acoustic sentiment metrics, speech rate offsets, and emotional empathy directive.",
        params_schema={"type": "object", "properties": {}},
        handler=get_vocal_affect_status,
        risk="auto",
    ))

    return active_synth
