"""Tests for Phase 6 BRIDGE: Telegram Bot Interface & Two-Way Voice Bridge."""

from unittest.mock import MagicMock, patch

from interface.telegram_bot import TelegramBot, _chunks


def test_chunks():
    short_text = "Hello world"
    assert list(_chunks(short_text, 100)) == ["Hello world"]

    long_text = "a" * 5000
    chunks = list(_chunks(long_text, 4096))
    assert len(chunks) == 2
    assert len(chunks[0]) == 4096
    assert len(chunks[1]) == 904


def test_telegram_unauthorized():
    mock_orch = MagicMock()
    bot = TelegramBot(mock_orch, allowed_ids=["12345"], token="dummy_token")

    with patch.object(bot, "_send") as mock_send:
        bot.handle_update({"message": {"chat": {"id": 99999}, "text": "hello"}})
        mock_send.assert_called_once()
        assert "Unauthorized" in mock_send.call_args[0][1]
        mock_orch.run_turn.assert_not_called()


def test_telegram_text_command():
    mock_orch = MagicMock()
    mock_orch.command.return_value = (False, "Briefing: all good")
    bot = TelegramBot(mock_orch, allowed_ids=["12345"], token="dummy_token")

    with patch.object(bot, "_send") as mock_send:
        bot.handle_update({"message": {"chat": {"id": 12345}, "text": "/briefing"}})
        mock_send.assert_called_once_with("12345", "Briefing: all good")


def test_telegram_text_chat():
    mock_orch = MagicMock()
    mock_orch.run_turn.return_value = {"reply": "Bilkul boss!"}
    mock_orch.config = {"voice": {"tts": {"enabled": False}}}
    bot = TelegramBot(mock_orch, allowed_ids=["12345"], token="dummy_token")

    with patch.object(bot, "_send") as mock_send:
        with patch.object(bot, "_api"):
            bot.handle_update({"message": {"chat": {"id": 12345}, "text": "kya haal hai"}})
            mock_send.assert_called_once_with("12345", "Bilkul boss!")
            mock_orch.run_turn.assert_called_once_with("kya haal hai")


def test_telegram_voice_note_bridge():
    mock_orch = MagicMock()
    mock_orch.run_turn.return_value = {"reply": "Voice directive completed."}
    mock_orch.config = {
        "voice": {
            "enabled": True,
            "whisper_model": "small",
            "language": "auto",
            "device": "auto",
            "tts": {"enabled": True, "voice": "hi-IN-MadhurNeural"},
        }
    }
    bot = TelegramBot(mock_orch, allowed_ids=["12345"], token="dummy_token")

    with patch.object(bot, "_download", return_value="dummy_path.oga"):
        with patch("voice.stt.transcribe", return_value="open notepad"):
            with patch.object(bot, "_send") as mock_send:
                with patch.object(bot, "_send_voice_audio") as mock_send_audio:
                    bot.handle_update({
                        "message": {
                            "chat": {"id": 12345},
                            "voice": {"file_id": "file_abc"},
                        }
                    })
                    mock_orch.run_turn.assert_called_once_with("open notepad")
                    mock_send.assert_called_once()
                    assert "🎙 open notepad" in mock_send.call_args[0][1]
                    mock_send_audio.assert_called_once_with("12345", "Voice directive completed.")
