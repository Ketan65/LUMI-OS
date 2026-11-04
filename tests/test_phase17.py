"""Unit & Integration tests for Phase 17: EMOTION-VOICE.

Tests:
  - Acoustic & linguistic sentiment analysis (Urgent, Debugging, Casual, Late Night)
  - Speech pacing calculation and Edge-TTS rate string modulation
  - Empathy directives for LLM persona conditioning
  - Manual overrides and telemetry retrieval
  - Emotion-Voice tools in ToolRegistry
  - FastAPI /api/voice/affect endpoints
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from tools.emotion_voice import register_emotion_voice_tools
from tools.registry import ToolRegistry
from voice.emotion_synthesizer import EmotionVoiceSynthesizer
from web.server import create_app


@pytest.fixture
def temp_emotion_synth() -> EmotionVoiceSynthesizer:
    return EmotionVoiceSynthesizer()


def test_sentiment_analysis_states(temp_emotion_synth: EmotionVoiceSynthesizer):
    # 1. Urgent detection
    res_urgent = temp_emotion_synth.analyze_utterance("Jaldi karo bhai, urgent emergency meeting hai!")
    assert res_urgent["state"] == "URGENT"
    assert res_urgent["speech_rate_offset"] == 15
    assert "rushed" in res_urgent["prompt_directive"].lower()
    assert temp_emotion_synth.get_adapted_tts_rate("+0%") == "+15%"

    # 2. Debugging frustration detection
    res_debug = temp_emotion_synth.analyze_utterance("Ye code crash ho raha hai, exception and error aa raha hai")
    assert res_debug["state"] == "FRUSTRATED_DEBUGGING"
    assert res_debug["speech_rate_offset"] == -5
    assert "calm" in res_debug["prompt_directive"].lower()
    assert temp_emotion_synth.get_adapted_tts_rate("+0%") == "-5%"

    # 3. Audio energy computation with synthetic wave
    audio_data = np.sin(np.linspace(0, 100, 1000)).astype(np.float32)
    res_audio = temp_emotion_synth.analyze_utterance("kaisa hai bhai", audio_samples=audio_data)
    assert res_audio["energy_rms"] > 0


def test_manual_override_and_prompt_directive(temp_emotion_synth: EmotionVoiceSynthesizer):
    # Set manual override
    temp_emotion_synth.set_mode(mode="urgent", pacing_offset=20)
    assert temp_emotion_synth.active_state == "URGENT"
    assert temp_emotion_synth.speech_rate_offset == 20
    assert "URGENT" in temp_emotion_synth.get_prompt_directive()

    # Reset
    temp_emotion_synth.set_mode(mode="auto")
    assert temp_emotion_synth.manual_override is None


def test_emotion_voice_tools_registration(temp_emotion_synth: EmotionVoiceSynthesizer):
    registry = ToolRegistry()
    registered_synth = register_emotion_voice_tools(registry, emotion_synth=temp_emotion_synth)
    assert registered_synth is temp_emotion_synth

    assert registry.get("detect_voice_affect") is not None
    assert registry.get("configure_vocal_affect") is not None
    assert registry.get("get_vocal_affect_status") is not None

    # Test tool handler
    detect_fn = registry.get("detect_voice_affect").handler
    res = detect_fn(utterance_text="Emergency server down!")
    assert res["state"] == "URGENT"

    cfg_fn = registry.get("configure_vocal_affect").handler
    c_res = cfg_fn(mode="calm", pacing_offset=-10)
    assert c_res["mode"] == "calm"
    assert c_res["speech_rate_offset"] == -10


@pytest.mark.asyncio
async def test_emotion_voice_web_api(temp_emotion_synth: EmotionVoiceSynthesizer):
    registry = ToolRegistry()
    register_emotion_voice_tools(registry, emotion_synth=temp_emotion_synth)

    mock_orch = MagicMock()
    mock_orch.config = {"web": {"allow_remote": True}}
    mock_orch.registry = registry
    mock_orch.emotion_voice = temp_emotion_synth

    app = create_app(mock_orch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. GET /api/voice/affect
        r = await client.get("/api/voice/affect")
        assert r.status_code == 200
        data = r.json()
        assert "active_state" in data

        # 2. POST /api/voice/affect/configure
        r_cfg = await client.post("/api/voice/affect/configure", json={"mode": "urgent", "pacing_offset": 15})
        assert r_cfg.status_code == 200
        cfg_data = r_cfg.json()
        assert cfg_data["mode"] == "urgent"
        assert cfg_data["speech_rate_offset"] == 15
