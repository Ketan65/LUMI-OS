"""Tests for Phase 2 EYES: Vision and Screen Perception tools."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from tools.registry import ToolRegistry
from tools.vision import (
    analyze_screen,
    analyze_screen_image,
    capture_screen,
    register_vision_tools,
)


def test_register_vision_tools():
    reg = ToolRegistry()
    register_vision_tools(reg)
    tool = reg.get("analyze_screen")
    assert tool is not None
    assert tool.name == "analyze_screen"
    assert tool.risk == "auto"
    assert "prompt" in tool.params_schema["properties"]


def test_analyze_screen_nonexistent_image():
    res = analyze_screen(image_path="non_existent_screen_123.jpg")
    assert "Error: Specified image path does not exist" in res


def test_analyze_screen_image_mocked(tmp_path):
    from PIL import Image

    img_path = tmp_path / "test.jpg"
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    img.save(img_path)

    # Mock OpenAI client
    mock_choice = MagicMock()
    mock_choice.message.content = "Detected a solid red square."
    mock_response = MagicMock(choices=[mock_choice])

    with patch("openai.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        with patch.dict("os.environ", {"NVIDIA_API_KEY": "test-key"}):
            result = analyze_screen_image(img_path, prompt="Describe color")
            assert "Detected a solid red square." in result


def test_capture_screen_fallback(tmp_path, monkeypatch):
    # Test that fallback returns False or latest when grab fails
    with patch("PIL.ImageGrab.grab", side_effect=OSError("screen grab failed")):
        with patch("mss.MSS", side_effect=Exception("BitBlt failed")):
            with patch("tools.vision.LATEST_SCREENSHOT", tmp_path / "nonexistent.jpg"):
                with patch("tools.vision.SCREENSHOTS_DIR", tmp_path):
                    ok, msg = capture_screen()
                    assert ok is False
                    assert "unavailable in headless background" in msg
