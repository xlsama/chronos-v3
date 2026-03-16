"""Tests for ImageDescriber — mock AsyncOpenAI."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.lib.image_describer import ImageDescriber, _get_mime_type


class TestGetMimeType:
    def test_png(self):
        assert _get_mime_type("photo.png") == "image/png"

    def test_jpg(self):
        assert _get_mime_type("photo.jpg") == "image/jpeg"

    def test_jpeg(self):
        assert _get_mime_type("photo.jpeg") == "image/jpeg"

    def test_webp(self):
        assert _get_mime_type("photo.webp") == "image/webp"

    def test_unknown_defaults_to_png(self):
        assert _get_mime_type("file.bmp") == "image/png"


class TestImageDescriber:
    @patch("src.lib.image_describer.get_settings")
    @patch("src.lib.image_describer.AsyncOpenAI")
    async def test_describe_sends_correct_request(self, mock_openai_cls, mock_settings):
        mock_settings.return_value = MagicMock(
            dashscope_api_key="test-key",
            llm_base_url="https://test.api",
            vision_model="qwen-vl-max",
        )

        mock_client = AsyncMock()
        mock_openai_cls.return_value = mock_client

        mock_choice = MagicMock()
        mock_choice.message.content = "A photo of a server rack"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        describer = ImageDescriber()
        result = await describer.describe(b"\x89PNG\r\n", "server.png")

        assert result == "A photo of a server rack"
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "qwen-vl-max"
        messages = call_kwargs["messages"]
        assert len(messages) == 1
        content = messages[0]["content"]
        assert content[0]["type"] == "image_url"
        assert "data:image/png;base64," in content[0]["image_url"]["url"]
        assert content[1]["type"] == "text"

    @patch("src.lib.image_describer.get_settings")
    @patch("src.lib.image_describer.AsyncOpenAI")
    async def test_describe_different_formats(self, mock_openai_cls, mock_settings):
        mock_settings.return_value = MagicMock(
            dashscope_api_key="test-key",
            llm_base_url="https://test.api",
            vision_model="qwen-vl-max",
        )

        mock_client = AsyncMock()
        mock_openai_cls.return_value = mock_client

        mock_choice = MagicMock()
        mock_choice.message.content = "description"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        describer = ImageDescriber()

        for fname, expected_mime in [
            ("img.jpg", "image/jpeg"),
            ("img.webp", "image/webp"),
            ("img.png", "image/png"),
        ]:
            await describer.describe(b"\x00" * 10, fname)
            call_kwargs = mock_client.chat.completions.create.call_args[1]
            url = call_kwargs["messages"][0]["content"][0]["image_url"]["url"]
            assert url.startswith(f"data:{expected_mime};base64,")
