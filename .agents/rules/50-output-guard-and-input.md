# Output guard and input rules (apply when editing `src/iir/guard/`, the API, the dashboard, or any code that accepts or returns text)

## Output guard runs last, on all outgoing text
Every LLM answer, API text field, report, and dashboard string passes the guard before it leaves the system.
- BLOCK (replace the whole response with a safe message): canary strings from the system prompt, stack traces, raw SQL in user-facing text.
- REDACT (replace the match with `[REDACTED:<CATEGORY>]`): API keys and bearer tokens, secret assignments such as `password=` or `client_secret=`, high-entropy strings over 24 characters, email addresses, phone numbers (including +94 formats), street addresses, device serial numbers (pattern in config), IP addresses, and local file paths.
- Pattern definitions live in `config/guard_patterns.yaml`.
- Log only the category and the count. Never log the matched value.
- The guard never raises. On internal error, return a generic safe message and log the error.
- False-positive check: normal engineering text such as `INV-07`, `412.5 W`, `58.2 C`, and timestamps must pass unchanged.

## Structured input
- Use the helper in `common/prompts.py` for CLI questions. Do not call `input()` directly in feature code.
- Each field has a validator and at most 3 attempts. On failure, re-prompt with a specific message.
- Reject control characters, except tab.
- Use `getpass` for any secret.
- Approval requires the full word `approve` or `reject`.

## Free-form text
- Maximum 4000 characters. Reject null bytes and binary content.
- Normalize to Unicode NFC. Strip control characters.
- Flag injection phrases such as "ignore previous instructions", "you are now", "reveal your prompt", and "call the executor". Record the flag. Flagged requests cannot approve or execute anything.
- Redact sensitive data before storage. Store the original text only with consent.
- Wrap user text in `<user_text>` tags, and escape `<` and `>` inside it.
- Responses are capped at about 600 words.

## Dashboard
- The dashboard reads from the API only. It holds its API key from the environment, never in the page or browser storage.
- Show model output as plain text. Never render it as HTML.
- Show Approve and Reject buttons only when the key has the approver role. The API still enforces the role.

## Tests you must write
- Each guard category has at least 3 positive and 3 negative examples.
- A canary in the output blocks the response.
- The original fake secret never appears in the guard's output.
- Every API route that returns text is covered by a guard test.
- At least 25 free-form injection examples. None may change the output schema or trigger the executor.
