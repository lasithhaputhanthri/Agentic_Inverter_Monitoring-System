"""In-memory rate limiter per API key / client.

Purpose: Enforces Rule 40:
         - 60 requests per minute per API key.
         - Returns 429 with Retry-After header when exceeded.
         - Automatically purges expired timestamps.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock


class RateLimiter:
    """Sliding-window rate limiter per client key."""

    def __init__(
        self,
        max_requests_per_minute: int = 60,
        window_seconds: float = 60.0,
    ) -> None:
        self.max_requests = max_requests_per_minute
        self.window_seconds = window_seconds
        self._history: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check_rate_limit(self, key: str, now: float | None = None) -> tuple[bool, int]:
        """Check if request is permitted under rate limit.

        Returns:
            (allowed: bool, retry_after_seconds: int)
        """
        current_time = now if now is not None else time.time()
        cutoff = current_time - self.window_seconds

        with self._lock:
            timestamps = self._history[key]

            # Drop timestamps outside the sliding window
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= self.max_requests:
                # Limit exceeded; calculate wait time until oldest request rolls off
                oldest = timestamps[0]
                retry_after = max(1, int(oldest + self.window_seconds - current_time) + 1)
                return False, retry_after

            # Record this request
            timestamps.append(current_time)
            return True, 0

    def reset(self) -> None:
        """Clear all rate limit history (useful for test suites)."""
        with self._lock:
            self._history.clear()


# Default global rate limiter instance
_global_rate_limiter: RateLimiter | None = None


def get_rate_limiter(max_per_minute: int = 60) -> RateLimiter:
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = RateLimiter(max_requests_per_minute=max_per_minute)
    return _global_rate_limiter
