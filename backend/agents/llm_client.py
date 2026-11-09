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
from backend.common.errors import LLMTimeoutError, LLMUnavailableError


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


class ProviderLLMClient:
    """Stub client for live LLM providers. Live execution requires explicit human authorization."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings(enforce_secrets=False)
        self.model_name = self.settings.llm_model

    def generate(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Guarded execution stub preventing unauthorized external network API calls."""
        del prompt, max_tokens, temperature
        raise LLMUnavailableError(
            "Live provider LLM calls are disabled in Phase 4. Explicit human checkpoint approval is required."
        )
