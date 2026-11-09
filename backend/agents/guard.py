"""Output guard and text scanner for LLM agent outputs.

Purpose: Sanitizes free-text fields in agent outputs, preventing credential leakage,
         canary disclosures, or control-character tampering.
Inputs: Raw text string (justification, evidence).
Outputs: Sanitized, redacted text string conforming to security guard rules.
"""

from __future__ import annotations

import re
import unicodedata

# Common credential patterns for redaction
SECRET_PATTERN = re.compile(
    r"(?i)(password\s*[:=]\s*\S+|api[_-]?key\s*[:=]\s*\S+|token\s*[:=]\s*\S+|bearer\s+[A-Za-z0-9\-._~+/]+=*)"
)
FILE_PATH_PATTERN = re.compile(r"([A-Za-z]:\\[\w\s\\.\-]+|/(?:etc|var|usr|home|tmp)/[\w\s/.\-]+)")


def scan_free_text(text: str) -> str:
    """Sanitize and scan free-text agent output before storage or display.

    - Normalizes Unicode NFC
    - Replaces null bytes and unsafe control characters
    - Redacts secret assignments and full system file paths
    - Preserves normal engineering text like 'INV-01', '230.1 V', '45.0 C'
    """
    if not text:
        return ""

    # Normalize Unicode NFC
    normalized = unicodedata.normalize("NFC", text)

    # Strip control characters except newline and tab
    sanitized = "".join(
        ch for ch in normalized if ch in "\n\t" or not unicodedata.category(ch).startswith("C")
    )

    # Redact secrets
    redacted = SECRET_PATTERN.sub("[REDACTED:SECRET]", sanitized)

    # Redact local system file paths
    redacted = FILE_PATH_PATTERN.sub("[REDACTED:PATH]", redacted)

    return redacted
