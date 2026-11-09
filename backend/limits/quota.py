"""Daily quotas and token budget enforcement.

Purpose: Enforces Rule 40:
         - 2000 requests per day per key.
         - 200 LLM calls per day per key.
         - 1,000,000 global daily token budget.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.storage.repositories import QuotaRepository

DEFAULT_MAX_REQUESTS_PER_DAY = 2000
DEFAULT_MAX_LLM_CALLS_PER_DAY = 200
DEFAULT_GLOBAL_TOKEN_BUDGET_DAILY = 1_000_000


class QuotaExceededError(Exception):
    """Raised when an API or LLM quota is breached."""

    pass


class QuotaManager:
    """Manages daily quotas and token consumption."""

    def __init__(
        self,
        max_daily_requests: int = DEFAULT_MAX_REQUESTS_PER_DAY,
        max_daily_llm_calls: int = DEFAULT_MAX_LLM_CALLS_PER_DAY,
        max_daily_tokens: int = DEFAULT_GLOBAL_TOKEN_BUDGET_DAILY,
    ) -> None:
        self.max_daily_requests = max_daily_requests
        self.max_daily_llm_calls = max_daily_llm_calls
        self.max_daily_tokens = max_daily_tokens

    def check_and_increment_request(self, session: Session, now: datetime | None = None) -> int:
        ref_time = now or datetime.now(UTC)
        date_str = ref_time.strftime("%Y-%m-%d")
        repo = QuotaRepository(session)
        count = repo.record_request(date_str)
        if count > self.max_daily_requests:
            raise QuotaExceededError("Daily request quota exceeded")
        return count

    def check_llm_quota(self, session: Session, now: datetime | None = None) -> None:
        ref_time = now or datetime.now(UTC)
        date_str = ref_time.strftime("%Y-%m-%d")
        repo = QuotaRepository(session)
        usage = repo.get_usage(date_str)
        if usage:
            if usage.llm_call_count >= self.max_daily_llm_calls:
                raise QuotaExceededError("daily analysis quota reached")
            if usage.tokens_used >= self.max_daily_tokens:
                raise QuotaExceededError("Global daily token budget exhausted")
