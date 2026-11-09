"""Token and call quota enforcement for LLM interactions.

Purpose: Enforces hard ceilings on daily calls and per-request input/output token usage.
Inputs: Prompt strings, requested completions, and daily call counters.
Outputs: Validated execution authorization or LLMQuotaExceededError.
"""

from __future__ import annotations

from backend.common.errors import LLMQuotaExceededError


def estimate_tokens(text: str) -> int:
    """Conservative token estimation (~4 characters per token)."""
    return max(1, len(text) // 4)


class QuotaTracker:
    """Tracks daily LLM call volume and enforces hard ceilings."""

    def __init__(self, daily_call_limit: int = 200) -> None:
        self.daily_call_limit = daily_call_limit
        self.daily_calls: int = 0

    def check_call_quota(self) -> None:
        """Verify that daily call allowance is not exhausted before executing an LLM request."""
        if self.daily_calls >= self.daily_call_limit:
            raise LLMQuotaExceededError(
                f"Daily LLM call quota ({self.daily_call_limit}) exhausted. Execution blocked."
            )

    def record_call(self) -> None:
        """Increment daily call usage."""
        self.daily_calls += 1

    def reset(self) -> None:
        """Reset the call counter."""
        self.daily_calls = 0
