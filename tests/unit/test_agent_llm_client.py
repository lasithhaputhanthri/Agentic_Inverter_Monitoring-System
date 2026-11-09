"""Unit tests for LLM client implementations and provider factory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from backend.agents.llm_client import (
    FakeLLMClient,
    GeminiLLMClient,
    ProviderLLMClient,
    create_llm_client,
)
from backend.common.config import Settings
from backend.common.errors import ConfigError, LLMTimeoutError, LLMUnavailableError


def test_create_llm_client_returns_fake_by_default() -> None:
    settings = Settings(llm_provider="mock", llm_model="mock-model")
    client = create_llm_client(settings)
    assert isinstance(client, FakeLLMClient)
    assert client.model_name == "mock-model"


def test_create_llm_client_returns_gemini_when_configured() -> None:
    settings = Settings(
        llm_provider="gemini",
        llm_model="gemini-2.5-flash",
        llm_api_key="valid_fake_test_key",
    )
    client = create_llm_client(settings)
    assert isinstance(client, GeminiLLMClient)
    assert client.model_name == "gemini-2.5-flash"


def test_gemini_client_raises_config_error_when_api_key_missing() -> None:
    with pytest.raises(ConfigError) as exc_info:
        GeminiLLMClient(api_key="", model_name="gemini-2.5-flash")
    assert "LLM_API_KEY" in str(exc_info.value)


def test_gemini_client_generate_success_mocked() -> None:
    client = GeminiLLMClient(api_key="valid_fake_key", model_name="gemini-2.5-flash")

    mock_response = MagicMock()
    mock_response.text = '{"cause": "overheating", "confidence": 0.95, "evidence": ["high temp"]}'
    mock_response.usage_metadata.prompt_token_count = 50
    mock_response.usage_metadata.candidates_token_count = 25

    mock_genai_client = MagicMock()
    mock_genai_client.models.generate_content.return_value = mock_response

    with patch.object(client, "_get_client", return_value=mock_genai_client):
        res = client.generate("Analyze this alert", max_tokens=200, temperature=0.0)

    assert res.text == mock_response.text
    assert res.input_tokens == 50
    assert res.output_tokens == 25
    assert res.model == "gemini-2.5-flash"
    assert res.latency_ms >= 0.0


def test_gemini_client_maps_timeout_and_error() -> None:
    client = GeminiLLMClient(api_key="valid_fake_key", model_name="gemini-2.5-flash")

    mock_genai_client = MagicMock()
    mock_genai_client.models.generate_content.side_effect = Exception("Deadline exceeded timeout")

    with patch.object(client, "_get_client", return_value=mock_genai_client):
        with pytest.raises(LLMTimeoutError):
            client.generate("test prompt")


def test_provider_client_delegates_to_gemini_or_mock() -> None:
    mock_settings = Settings(llm_provider="mock", llm_model="test-mock")
    prov_mock = ProviderLLMClient(mock_settings)
    assert isinstance(prov_mock._delegate, FakeLLMClient)

    gemini_settings = Settings(
        llm_provider="gemini",
        llm_model="gemini-2.5-flash",
        llm_api_key="valid_fake_key",
    )
    prov_gemini = ProviderLLMClient(gemini_settings)
    assert isinstance(prov_gemini._delegate, GeminiLLMClient)


def test_provider_client_raises_for_unsupported_provider() -> None:
    bad_settings = Settings(llm_provider="unsupported_vendor")
    with pytest.raises(LLMUnavailableError):
        ProviderLLMClient(bad_settings)
