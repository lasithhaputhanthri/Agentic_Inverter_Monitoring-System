"""LLM client protocols, fake implementation, and provider stub.

Purpose: Abstracts LLM interactions through a standard interface, preventing vendor lock-in
         and ensuring tests use deterministic scripted fakes without network or credential access.
Inputs: Formatted prompts and operational token limits.
Outputs: LLMResponse dataclass containing text, token usage, model ID, and latency.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

from backend.common.config import Settings, load_settings
from backend.common.errors import ConfigError, LLMTimeoutError, LLMUnavailableError


@dataclass(frozen=True)
class LLMResponse:
    """Standardized response from an LLM inference call."""

    text: str
    input_tokens: int
    output_tokens: int
    model: str
    latency_ms: float


class LLMClient(Protocol):
    """Protocol defining the interface for all language model clients."""

    def generate(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Execute a text completion or structured generation request against the model."""
        ...


class FakeLLMClient:
    """Scriptable mock LLM client for testing agents, error handling, retries, and quotas."""

    def __init__(
        self,
        scripted_responses: list[str] | None = None,
        default_response: str = '{"cause": "unknown", "confidence": 0.5, "evidence": ["default"]}',
        model_name: str = "fake-model",
    ) -> None:
        self.scripted_responses: list[str] = list(scripted_responses) if scripted_responses else []
        self.default_response = default_response
        self.model_name = model_name
        self.call_count: int = 0
        self.calls: list[dict[str, Any]] = []
        self.simulate_timeout: bool = False
        self.simulate_malformed: bool = False
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0

    def queue_response(self, response_text: str) -> None:
        """Enqueue a scripted response for the next generate call."""
        self.scripted_responses.append(response_text)

    def generate(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Return scripted response or simulate operational failures."""
        self.call_count += 1
        call_record = {
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "timestamp": time.time(),
        }
        self.calls.append(call_record)

        if self.simulate_timeout:
            raise LLMTimeoutError("Simulated LLM call timeout")

        if self.simulate_malformed:
            raw_text = "INVALID_JSON_OUTPUT_MALFORMED"
        elif self.scripted_responses:
            raw_text = self.scripted_responses.pop(0)
        else:
            raw_text = self.default_response

        # Rough token approximation for mock accounting (4 chars per token)
        in_tok = max(1, len(prompt) // 4)
        out_tok = max(1, len(raw_text) // 4)
        self.total_input_tokens += in_tok
        self.total_output_tokens += out_tok

        return LLMResponse(
            text=raw_text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            model=self.model_name,
            latency_ms=15.0,
        )


class GeminiLLMClient:
    """Client for Google Gemini models using the official google-genai SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "gemini-2.5-flash",
    ) -> None:
        if not api_key or api_key == "placeholder_llm_api_key":
            raise ConfigError(
                "LLM_API_KEY",
                "A valid Gemini API key is required when LLM_PROVIDER is 'gemini'. Set LLM_API_KEY in your .env file.",
            )
        self.api_key = api_key
        self.model_name = model_name
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from google import genai

                self._client = genai.Client(api_key=self.api_key)
            except ImportError as err:
                raise LLMUnavailableError(
                    "The 'google-genai' package is required for the Gemini provider: pip install google-genai"
                ) from err
        return self._client

    def generate(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Call Google Gemini model and return standardized LLMResponse."""
        from google.genai import types

        start_time = time.time()
        client = self._get_client()

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens or 300,
        )

        try:
            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
        except Exception as exc:
            err_msg = str(exc)
            if "deadline" in err_msg.lower() or "timeout" in err_msg.lower():
                raise LLMTimeoutError(f"Gemini API request timed out: {exc}") from exc
            raise LLMUnavailableError(f"Gemini API request failed: {exc}") from exc

        latency_ms = (time.time() - start_time) * 1000.0
        raw_text = response.text or ""

        in_tok = max(1, len(prompt) // 4)
        out_tok = max(1, len(raw_text) // 4)
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            prompt_tokens = getattr(response.usage_metadata, "prompt_token_count", None)
            cand_tokens = getattr(response.usage_metadata, "candidates_token_count", None)
            if prompt_tokens is not None:
                in_tok = prompt_tokens
            if cand_tokens is not None:
                out_tok = cand_tokens

        return LLMResponse(
            text=raw_text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            model=self.model_name,
            latency_ms=latency_ms,
        )


class ProviderLLMClient:
    """Client for external LLM providers (e.g. Gemini) configured via settings."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings(enforce_secrets=False)
        self.provider = self.settings.llm_provider.lower().strip()
        self.model_name = self.settings.llm_model

        if self.provider == "gemini":
            self._delegate: LLMClient = GeminiLLMClient(
                api_key=self.settings.llm_api_key,
                model_name=self.settings.llm_model or "gemini-2.5-flash",
            )
        elif self.provider == "mock":
            self._delegate = FakeLLMClient(model_name=self.model_name or "mock-model")
        else:
            raise LLMUnavailableError(
                f"Unsupported LLM provider '{self.provider}'. Supported providers: 'mock', 'gemini'."
            )

    def generate(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Forward text generation call to the underlying provider client."""
        return self._delegate.generate(prompt, max_tokens=max_tokens, temperature=temperature)


def create_llm_client(settings: Settings | None = None) -> LLMClient:
    """Instantiate an LLM client based on application configuration."""
    settings = settings or load_settings(enforce_secrets=False)
    provider = settings.llm_provider.lower().strip()
    if provider == "gemini":
        return GeminiLLMClient(
            api_key=settings.llm_api_key,
            model_name=settings.llm_model or "gemini-2.5-flash",
        )
    return FakeLLMClient(model_name=settings.llm_model or "mock-model")
