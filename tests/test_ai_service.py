"""
Tests for the AI Service module.
"""

import pytest
import sys
import os
import json
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch, Mock
import httpx

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_service import AIService, AIConfig, get_ai_service, reset_ai_service


class TestAIConfig:
    """Tests for AIConfig dataclass."""

    def test_default_config(self):
        """Test default AIConfig initialization."""
        config = AIConfig()
        assert config.provider == "ollama"
        assert config.ollama_base_url == "http://localhost:11434"
        assert config.ollama_model == "gpt-oss:120b-cloud"
        assert config.gemini_api_key == ""
        assert config.gemini_model == "gemini-1.5-flash"

    def test_custom_ollama_config(self):
        """Test custom Ollama configuration."""
        config = AIConfig(
            provider="ollama",
            ollama_base_url="http://192.168.1.100:11434",
            ollama_model="llama3.2"
        )
        assert config.provider == "ollama"
        assert config.ollama_base_url == "http://192.168.1.100:11434"
        assert config.ollama_model == "llama3.2"

    def test_custom_gemini_config(self):
        """Test custom Gemini configuration."""
        config = AIConfig(
            provider="gemini",
            gemini_api_key="test_key_123",
            gemini_model="gemini-2.0"
        )
        assert config.provider == "gemini"
        assert config.gemini_api_key == "test_key_123"
        assert config.gemini_model == "gemini-2.0"


class TestAIServiceInitialization:
    """Tests for AIService initialization."""

    def test_init_with_default_config(self):
        """Test AIService initialization with default config."""
        service = AIService()
        assert service.config.provider == "ollama"
        assert service._client is None

    def test_init_with_custom_config(self):
        """Test AIService initialization with custom config."""
        config = AIConfig(provider="gemini", gemini_api_key="test_key")
        service = AIService(config=config)
        assert service.config.provider == "gemini"
        assert service.config.gemini_api_key == "test_key"

    @patch.dict(os.environ, {"GEMINI_API_KEY": "env_test_key"})
    def test_config_load_from_environment(self):
        """Test loading config from environment variable."""
        with patch("ai_service.os.path.exists", return_value=False):
            service = AIService()
            assert service.config.gemini_api_key == "env_test_key"

    def test_config_load_from_file(self):
        """Test loading config from ai_config.json file."""
        config_data = {
            "provider": "gemini",
            "ollama": {
                "base_url": "http://ollama.local:11434",
                "model": "custom_model"
            },
            "gemini": {
                "api_key": "file_key_123",
                "model": "gemini-1.5-pro"
            }
        }

        with patch("builtins.open", ) as mock_open:
            m = MagicMock()
            m.__enter__.return_value.read.return_value = json.dumps(config_data)
            mock_open.return_value = m

            with patch("ai_service.os.path.exists", return_value=True):
                service = AIService()
                service.config._load_config = lambda: AIConfig(
                    provider="gemini",
                    gemini_api_key="file_key_123"
                )

    def test_config_fallback_on_file_error(self):
        """Test fallback to default config when file read fails."""
        with patch("ai_service.os.path.exists", return_value=True):
            with patch("builtins.open", side_effect=Exception("File error")):
                service = AIService()
                # Should still have a valid config
                assert service.config is not None


class TestAIServiceConfigPersistence:
    """Tests for config saving and loading."""

    def test_save_config_to_file(self):
        """Test saving configuration to file."""
        config = AIConfig(
            provider="gemini",
            gemini_api_key="test_api_key",
            ollama_base_url="http://test:11434"
        )
        service = AIService(config=config)

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "ai_config.json")

            with patch("ai_service.os.path.dirname", return_value=tmpdir):
                with patch("builtins.open", create=True) as mock_file:
                    service.save_config()
                    # Verify that open was called with write mode
                    mock_file.assert_called()


@pytest.mark.asyncio
class TestAIServiceAvailability:
    """Tests for check_availability method."""

    async def test_ollama_available(self):
        """Test checking Ollama availability when it's running."""
        config = AIConfig(provider="ollama")
        service = AIService(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3.2:latest"},
                {"name": "gpt-oss:120b-cloud"}
            ]
        }

        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await service.check_availability()

            assert result["available"] is True
            assert result["provider"] == "ollama"
            assert result["model"] == "gpt-oss:120b-cloud"
            assert result["error"] is None

    async def test_ollama_model_not_found(self):
        """Test Ollama when configured model is not available."""
        config = AIConfig(
            provider="ollama",
            ollama_model="missing_model"
        )
        service = AIService(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [{"name": "llama3.2:latest"}]
        }

        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await service.check_availability()

            assert result["available"] is True
            assert "not found" in result["error"].lower() or result["error"] is None

    async def test_ollama_connection_error(self):
        """Test Ollama when connection fails."""
        config = AIConfig(provider="ollama")
        service = AIService(config=config)

        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_get_client.return_value = mock_client

            result = await service.check_availability()

            assert result["available"] is False
            assert result["error"] is not None
            assert "connect" in result["error"].lower()

    async def test_gemini_available(self):
        """Test checking Gemini availability with valid API key."""
        config = AIConfig(provider="gemini", gemini_api_key="valid_key")
        service = AIService(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"models": []}

        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await service.check_availability()

            assert result["available"] is True
            assert result["provider"] == "gemini"

    async def test_gemini_no_api_key(self):
        """Test Gemini availability without API key."""
        config = AIConfig(provider="gemini", gemini_api_key="")
        service = AIService(config=config)

        result = await service.check_availability()

        assert result["available"] is False
        assert "api key" in result["error"].lower()

    async def test_gemini_invalid_api_key(self):
        """Test Gemini with invalid API key."""
        config = AIConfig(provider="gemini", gemini_api_key="invalid_key")
        service = AIService(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": {"message": "API key invalid"}}

        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await service.check_availability()

            assert result["available"] is False
            assert "invalid" in result["error"].lower()


@pytest.mark.asyncio
class TestAIServiceGeneration:
    """Tests for prompt generation and API calls."""

    async def test_ask_with_context(self):
        """Test asking a question with context."""
        config = AIConfig(provider="ollama")
        service = AIService(config=config)

        question = "What is this about?"
        context = "This is a great book about AI."
        book_title = "AI Guide"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "It's about artificial intelligence."}

        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await service.ask(question, context, book_title)

            assert result == "It's about artificial intelligence."
            mock_client.post.assert_called_once()

    async def test_ask_without_book_title(self):
        """Test asking a question without book title."""
        config = AIConfig(provider="ollama")
        service = AIService(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "Here's the answer"}

        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await service.ask("What?", "Context text")

            assert result == "Here's the answer"

    async def test_summarize_concise(self):
        """Test summarizing with concise style."""
        config = AIConfig(provider="ollama")
        service = AIService(config=config)

        text = "Long chapter text with many sentences..."

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "Summary in 2-3 sentences"}

        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await service.summarize(text, style="concise")

            assert result == "Summary in 2-3 sentences"

    async def test_summarize_detailed(self):
        """Test summarizing with detailed style."""
        config = AIConfig(provider="ollama")
        service = AIService(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "Detailed summary..."}

        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await service.summarize("Long text", style="detailed")

            assert result == "Detailed summary..."

    async def test_summarize_bullets(self):
        """Test summarizing with bullets style."""
        config = AIConfig(provider="ollama")
        service = AIService(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "• Point 1\n• Point 2"}

        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await service.summarize("Text", style="bullets")

            assert "Point" in result

    async def test_explain(self):
        """Test explaining text."""
        config = AIConfig(provider="ollama")
        service = AIService(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "Simple explanation"}

        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await service.explain("Complex concept")

            assert result == "Simple explanation"

    async def test_define_without_context(self):
        """Test defining a word without context."""
        config = AIConfig(provider="ollama")
        service = AIService(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "Definition of word"}

        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await service.define("word")

            assert result == "Definition of word"

    async def test_define_with_context(self):
        """Test defining a word with context."""
        config = AIConfig(provider="ollama")
        service = AIService(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "Context-specific definition"}

        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await service.define("word", context="The word was used in...")

            assert "definition" in result.lower()


@pytest.mark.asyncio
class TestAIServiceOllamaGeneration:
    """Tests for Ollama-specific generation."""

    async def test_ollama_generate_success(self):
        """Test successful Ollama generation."""
        config = AIConfig(provider="ollama")
        service = AIService(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "Ollama response"}

        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await service._ollama_generate("Test prompt")

            assert result == "Ollama response"
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert "api/generate" in call_args[0][0]

    async def test_ollama_generate_error(self):
        """Test Ollama generation error handling."""
        config = AIConfig(provider="ollama")
        service = AIService(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server error"

        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            with pytest.raises(Exception, match="Ollama error"):
                await service._ollama_generate("Test prompt")

    async def test_ollama_request_format(self):
        """Test Ollama request format."""
        config = AIConfig(
            provider="ollama",
            ollama_model="test_model"
        )
        service = AIService(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "Test"}

        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            await service._ollama_generate("Test prompt")

            call_args = mock_client.post.call_args
            json_payload = call_args[1]["json"]
            assert json_payload["model"] == "test_model"
            assert json_payload["prompt"] == "Test prompt"
            assert json_payload["stream"] is False
            assert "options" in json_payload


@pytest.mark.asyncio
class TestAIServiceGeminiGeneration:
    """Tests for Gemini-specific generation."""

    async def test_gemini_generate_success(self):
        """Test successful Gemini generation."""
        config = AIConfig(
            provider="gemini",
            gemini_api_key="test_key"
        )
        service = AIService(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "Gemini response"}
                        ]
                    }
                }
            ]
        }

        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await service._gemini_generate("Test prompt")

            assert result == "Gemini response"

    async def test_gemini_generate_no_api_key(self):
        """Test Gemini generation without API key."""
        config = AIConfig(provider="gemini", gemini_api_key="")
        service = AIService(config=config)

        with pytest.raises(Exception, match="API key"):
            await service._gemini_generate("Test prompt")

    async def test_gemini_api_error(self):
        """Test Gemini API error handling."""
        config = AIConfig(
            provider="gemini",
            gemini_api_key="invalid_key"
        )
        service = AIService(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": {
                "message": "Invalid request"
            }
        }

        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            with pytest.raises(Exception, match="Gemini error"):
                await service._gemini_generate("Test prompt")

    async def test_gemini_empty_response(self):
        """Test Gemini with empty candidates."""
        config = AIConfig(
            provider="gemini",
            gemini_api_key="test_key"
        )
        service = AIService(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"candidates": []}

        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            result = await service._gemini_generate("Test prompt")

            assert result == ""

    async def test_gemini_request_format(self):
        """Test Gemini request format."""
        config = AIConfig(
            provider="gemini",
            gemini_api_key="test_key",
            gemini_model="gemini-1.5-flash"
        )
        service = AIService(config=config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "Response"}
                        ]
                    }
                }
            ]
        }

        with patch.object(service, '_get_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            await service._gemini_generate("Test prompt")

            call_args = mock_client.post.call_args
            assert "gemini-1.5-flash" in call_args[0][0]
            json_payload = call_args[1]["json"]
            assert "contents" in json_payload
            assert json_payload["contents"][0]["parts"][0]["text"] == "Test prompt"


@pytest.mark.asyncio
class TestAIServiceClientManagement:
    """Tests for HTTP client lifecycle management."""

    async def test_client_creation(self):
        """Test lazy client creation."""
        service = AIService()
        assert service._client is None

        client = await service._get_client()
        assert client is not None
        assert isinstance(client, httpx.AsyncClient)

    async def test_client_persistence(self):
        """Test that client is reused between calls."""
        service = AIService()

        client1 = await service._get_client()
        client2 = await service._get_client()

        assert client1 is client2

    async def test_client_close(self):
        """Test closing the client."""
        service = AIService()
        client = await service._get_client()
        await service.close()

        assert service._client is None or service._client.is_closed

    async def test_multiple_close_calls(self):
        """Test that multiple close calls don't raise errors."""
        service = AIService()
        await service._get_client()
        await service.close()
        await service.close()  # Should not raise


@pytest.mark.asyncio
class TestAIServiceSingleton:
    """Tests for AI service singleton pattern."""

    def test_singleton_creation(self):
        """Test that get_ai_service creates a singleton."""
        reset_ai_service()
        service1 = get_ai_service()
        service2 = get_ai_service()

        assert service1 is service2

    def test_reset_singleton(self):
        """Test resetting the singleton."""
        service1 = get_ai_service()
        reset_ai_service()
        service2 = get_ai_service()

        assert service1 is not service2


class TestPromptBuilding:
    """Tests for prompt building methods."""

    def test_build_ask_prompt_with_title(self):
        """Test ask prompt building with book title."""
        service = AIService()
        prompt = service._build_ask_prompt("What is X?", "Context text", "Book Title")

        assert "What is X?" in prompt
        assert "Context text" in prompt
        assert "Book Title" in prompt

    def test_build_ask_prompt_without_title(self):
        """Test ask prompt building without book title."""
        service = AIService()
        prompt = service._build_ask_prompt("What is X?", "Context text", "")

        assert "What is X?" in prompt
        assert "Context text" in prompt
        assert "Book Title" not in prompt

    def test_build_summarize_prompt_concise(self):
        """Test summarize prompt building for concise style."""
        service = AIService()
        prompt = service._build_summarize_prompt("Long text", "concise")

        assert "2-3 sentences" in prompt or "concise" in prompt.lower()
        assert "Long text" in prompt

    def test_build_summarize_prompt_detailed(self):
        """Test summarize prompt building for detailed style."""
        service = AIService()
        prompt = service._build_summarize_prompt("Long text", "detailed")

        assert "detailed" in prompt.lower() or "multiple" in prompt.lower()
        assert "Long text" in prompt

    def test_build_summarize_prompt_bullets(self):
        """Test summarize prompt building for bullets style."""
        service = AIService()
        prompt = service._build_summarize_prompt("Long text", "bullets")

        assert "bullet" in prompt.lower() or "point" in prompt.lower()
        assert "Long text" in prompt
