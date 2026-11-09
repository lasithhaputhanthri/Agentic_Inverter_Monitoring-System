"""Standardized logging with sensitive credential redaction.

Purpose: Formats log output and strips secrets, passwords, tokens, and API keys.
Inputs: LogRecord objects and formatted messages.
Outputs: Sanitized LogRecord instances with sensitive substrings redacted.
"""

from __future__ import annotations

import logging
import re

REDACTED_LABEL: str = "[REDACTED]"

# Regex patterns matching key-like strings and assignments
ASSIGNMENT_PATTERN: re.Pattern[str] = re.compile(
    r"""(?i)\b(password|secret|client_secret|api_key|pepper|token)\s*=\s*(['"]?)([^'"\s,;]+)\2"""
)

KEY_PATTERN: re.Pattern[str] = re.compile(
    r"""(?i)\b(bearer\s+|api[_-]?key[=:\s]+|token[=:\s]+)(['"]?)([a-zA-Z0-9_\-\.]{8,})\2"""
)

HIGH_ENTROPY_PATTERN: re.Pattern[str] = re.compile(
    r"""\b(?:sk-[a-zA-Z0-9_\-]{16,}|[a-zA-Z0-9]{32,})\b"""
)


def redact_text(text: str) -> str:
    """Redact passwords, secret assignments, and key-like patterns from text.

    Normal engineering tokens such as INV-07, 412.5 W, 58.2 C must remain unchanged.
    """
    if not text:
        return text

    # Redact assignments e.g. password=abc12345 or secret="mysecret"
    sanitized = ASSIGNMENT_PATTERN.sub(rf"\1={REDACTED_LABEL}", text)

    # Redact explicit bearer or api-key prefixes
    sanitized = KEY_PATTERN.sub(rf"\1{REDACTED_LABEL}", sanitized)

    # Redact high entropy API keys like sk-... or 32+ char hex/base64 strings
    sanitized = HIGH_ENTROPY_PATTERN.sub(REDACTED_LABEL, sanitized)

    return sanitized


class RedactingFilter(logging.Filter):
    """Log filter that strips sensitive credential substrings from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            formatted = record.getMessage()
            record.msg = redact_text(formatted)
            record.args = None
        except Exception:
            if isinstance(record.msg, str):
                record.msg = redact_text(record.msg)

        return True


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured with RedactingFilter."""
    logger = logging.getLogger(name)
    if not any(isinstance(f, RedactingFilter) for f in logger.filters):
        logger.addFilter(RedactingFilter())
    return logger


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logging with RedactingFilter and standard formatting."""
    root = logging.getLogger()
    root.setLevel(level)

    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.addFilter(RedactingFilter())

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s")
    handler.setFormatter(formatter)

    # Avoid duplicate handlers
    root.handlers.clear()
    root.addHandler(handler)
