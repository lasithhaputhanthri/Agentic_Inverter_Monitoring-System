# Limits and load rules (apply when editing `src/iir/limits/`, `src/iir/api/`, or the alert queue)

## Default limits (read from config, never hard-code)
- Requests per minute per API key: 60. Exceeding it returns HTTP 429 with `Retry-After`.
- Requests per day per key: 2000.
- LLM calls per day per key: 200. Exceeding it returns HTTP 429 with the message "daily analysis quota reached".
- Concurrent jobs per key: 2.
- Maximum request body: 16 KB (HTTP 413 if exceeded).
- Maximum free-text length: 4000 characters (HTTP 422).
- List endpoints clamp `limit` to 200 rather than rejecting it.

## Token budgets
- Per run: 200 000 tokens. Once reached, remaining alerts are marked `budget_exhausted`, and the LLM is not called.
- Per day, global: 1 000 000 tokens. This is a hard stop, and the operator is alerted.
- Record tokens, latency, model, prompt hash, and outcome for every LLM call in `llm_calls`.

## Load control
- At most 4 LLM calls run at once (semaphore).
- The alert queue holds at most 50 items. When it is full, new alerts are recorded as `deferred`, not dropped.
- Per-device alert cooldown: 300 seconds. One fault produces one alert.
- Provider retries: at most 3 attempts with exponential backoff and jitter. Never retry a 4xx error.
- Circuit breaker: after 5 consecutive failures within 60 seconds, open for 60 seconds. While open, defer alerts. Never drop them.
- Timeouts: 20 seconds for LLM calls. Set a timeout on every database call.
- Cache diagnosis results by a hash of the sanitized features, the prompt version, and the model name. Expire entries after 24 hours. Disable the cache during variance experiments and say so in the report.

## Tests you must write
- Rate limit: the 61st request in a minute returns 429, and the limit resets after the window.
- Quota: the call is blocked before it is made. Check this with the fake client's call count.
- Breaker: it opens, defers alerts, and closes after its timeout.
- Cooldown: a persistent fault produces one alert per cooldown window.
- Oversized body returns 413.
- Load test: 20 devices at 15-second intervals for 1 simulated hour, plus a burst of 10 alerts. Assert that the queue never exceeds its bound, nothing is silently dropped, and the LLM call count stays within quota. Write the p50 and p95 results to `docs/baseline/load_v1.json`.
