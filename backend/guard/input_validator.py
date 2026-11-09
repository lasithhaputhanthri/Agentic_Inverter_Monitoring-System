"""Input validation and sanitization for free-form user and operator text.

Purpose: Enforces Rule 50:
         - Max 4000 characters.
         - Reject null bytes and binary content.
         - Normalize to Unicode NFC and strip disallowed control characters.
         - Detect prompt injection phrases ("ignore previous instructions", "you are now", etc.).
         - Wrap text in <user_text> tags with escaped HTML delimiters.
"""

from __future__ import annotations

import unicodedata
from typing import NamedTuple

from backend.guard.output_guard import get_output_guard

MAX_FREE_TEXT_LENGTH = 4000

INJECTION_PHRASES = [
    "ignore previous instructions",
    "you are now",
    "reveal your prompt",
    "call the executor",
    "system override",
    "disregard all previous rules",
]


class ValidatedInput(NamedTuple):
    sanitized_text: str
    wrapped_text: str
    is_injection_flagged: bool


class InputValidationError(ValueError):
    """Raised when free-form text fails security validation rules."""

    pass


def scan_free_text(text: str) -> ValidatedInput:
    """Validate, normalize, scan for injection, and wrap free-form user/operator text."""
    if not isinstance(text, str):
        raise InputValidationError("Input must be a valid text string")

    # 1. Null bytes & binary content check
    if "\x00" in text:
        raise InputValidationError("Null bytes are strictly prohibited in text input")

    # 2. Length check
    if len(text) > MAX_FREE_TEXT_LENGTH:
        raise InputValidationError(
            f"Text length exceeds maximum allowed length of {MAX_FREE_TEXT_LENGTH} characters"
        )

    # 3. Unicode NFC Normalization
    normalized = unicodedata.normalize("NFC", text)

    # 4. Strip control characters (allow tab, newline, carriage return)
    cleaned_chars = [
        c for c in normalized if unicodedata.category(c)[0] != "C" or c in ("\t", "\n", "\r")
    ]
    cleaned = "".join(cleaned_chars)

    # 5. Check for injection phrases
    lower_cleaned = cleaned.lower()
    flagged = any(phrase in lower_cleaned for phrase in INJECTION_PHRASES)

    # 6. Redact any sensitive tokens before further processing or storage
    guard = get_output_guard()
    sanitized = guard.sanitize_text(cleaned)

    # 7. Escape < and > and wrap in <user_text> tags
    escaped = sanitized.replace("<", "&lt;").replace(">", "&gt;")
    wrapped = f"<user_text>{escaped}</user_text>"

    return ValidatedInput(
        sanitized_text=sanitized,
        wrapped_text=wrapped,
        is_injection_flagged=flagged,
    )
