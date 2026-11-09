"""Output guard for outgoing API responses, reports, and UI content.

Purpose: Enforces Rule 50 and SEC-50:
         - BLOCK: canary strings, stack traces, raw SQL queries.
         - REDACT: API keys, secrets, high-entropy tokens, emails, phone numbers,
                   addresses, device serials, IP addresses, file paths.
         - Never raises: on error returns safe text.
         - Preserves normal engineering text (e.g., INV-07, 412.5 W, 58.2 C, timestamps, UUIDs).
"""

from __future__ import annotations

import logging
import math
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path("config/guard_patterns.yaml")
SAFE_FALLBACK_BLOCK = "[BLOCKED: Sensitive content detected]"
UUID_REGEX = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def calculate_entropy(text: str) -> float:
    """Calculate Shannon entropy for a given string."""
    if not text:
        return 0.0
    freq: dict[str, int] = {}
    for c in text:
        freq[c] = freq.get(c, 0) + 1
    length = len(text)
    return -sum((count / length) * math.log2(count / length) for count in freq.values())


class OutputGuard:
    """Sanitizer for outgoing text and structured responses."""

    def __init__(self, config_path: Path | str | None = None) -> None:
        self.block_patterns: list[tuple[str, re.Pattern[str]]] = []
        self.redact_patterns: list[tuple[str, str, re.Pattern[str]]] = []
        self._load_patterns(config_path or DEFAULT_CONFIG_PATH)

    def _load_patterns(self, config_path: Path | str) -> None:
        path = Path(config_path)
        if not path.is_file():
            # Fallback default regexes if config file is not found
            self._load_fallback_patterns()
            return

        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            for item in data.get("block_patterns", []):
                self.block_patterns.append(
                    (
                        item["name"],
                        re.compile(
                            item["regex"], re.IGNORECASE if "(?i)" not in item["regex"] else 0
                        ),
                    )
                )

            for item in data.get("redact_patterns", []):
                self.redact_patterns.append(
                    (
                        item["name"],
                        item["category"],
                        re.compile(item["regex"]),
                    )
                )
        except Exception as e:
            logger.error("Failed to load guard patterns from %s: %s", path, e)
            self._load_fallback_patterns()

    def _load_fallback_patterns(self) -> None:
        self.block_patterns = [
            ("canary_token", re.compile(r"CANARY-[A-Z0-9_-]{16,}", re.IGNORECASE)),
            ("stack_trace", re.compile(r"Traceback \(most recent call last\):")),
            (
                "raw_sql",
                re.compile(
                    r"\b(SELECT\s+.+\s+FROM|INSERT\s+INTO\s+.+\s+VALUES|DELETE\s+FROM|DROP\s+TABLE)\b",
                    re.IGNORECASE,
                ),
            ),
        ]
        self.redact_patterns = [
            (
                "api_key",
                "API_KEY",
                re.compile(
                    r"(?i)(?:bearer\s+[a-zA-Z0-9_\-\.]{20,}|(?:sk|pk|api|key)[-_][a-zA-Z0-9_\-]{16,})"
                ),
            ),
            (
                "secret_assignment",
                "SECRET",
                re.compile(
                    r'(?i)(?:password|client_secret|access_token|secret_key)\s*[:=]\s*["\'][^"\']+["\']'
                ),
            ),
            ("email", "EMAIL", re.compile(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b")),
            (
                "phone",
                "PHONE",
                re.compile(
                    r"(?:\+94|0094|0)\s*(?:7[0-9]{8}|[1-9][0-9]{8}|[1-9][0-9]{1}[-\s]?[0-9]{7})\b"
                ),
            ),
            (
                "street_address",
                "ADDRESS",
                re.compile(
                    r"\b\d{1,5}\s+[A-Za-z0-9\s,]+(?:Street|St\.|Avenue|Ave\.|Road|Rd\.|Boulevard|Blvd\.|Lane|Ln\.|Drive|Dr\.)\b"
                ),
            ),
            ("device_serial", "SERIAL", re.compile(r"\bINV-SN-[A-Za-z0-9]{8,16}\b")),
            (
                "ip_address",
                "IP_ADDRESS",
                re.compile(
                    r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"
                ),
            ),
            (
                "file_path",
                "FILE_PATH",
                re.compile(
                    r"(?:\b[A-Za-z]:\\[a-zA-Z0-9_.\-\\]{3,}|/(?:home|etc|var|usr|Users|tmp)/[a-zA-Z0-9_.\-/]+)"
                ),
            ),
            ("high_entropy", "HIGH_ENTROPY", re.compile(r"\b[A-Za-z0-9_-]{32,}\b")),
        ]

    def sanitize_text(self, text: str) -> str:
        """Sanitize an individual text string by blocking or redacting sensitive tokens."""
        if not text:
            return text

        try:
            # 1. Block Check
            for name, pattern in self.block_patterns:
                if pattern.search(text):
                    logger.warning("Guard BLOCKED content matching category: %s", name)
                    return SAFE_FALLBACK_BLOCK

            sanitized = text

            # 2. Redact Check
            for name, category, pattern in self.redact_patterns:
                if name == "high_entropy":
                    # Special check for high entropy strings: don't redact UUIDs or normal words
                    def replace_entropy(m: re.Match[str], cat: str = category) -> str:
                        val = m.group(0)
                        if UUID_REGEX.match(val):
                            return val
                        # Check Shannon entropy (random keys typically > 4.2 bits per char)
                        if calculate_entropy(val) > 3.8:
                            return f"[REDACTED:{cat}]"
                        return val

                    sanitized = pattern.sub(replace_entropy, sanitized)
                else:
                    sanitized = pattern.sub(f"[REDACTED:{category}]", sanitized)

            return sanitized
        except Exception as e:
            logger.error("Error during text sanitization: %s", e)
            return SAFE_FALLBACK_BLOCK

    def sanitize(self, data: Any) -> Any:
        """Recursively sanitize dicts, lists, and strings."""
        try:
            if isinstance(data, str):
                return self.sanitize_text(data)
            elif isinstance(data, dict):
                return {k: self.sanitize(v) for k, v in data.items()}
            elif isinstance(data, list):
                return [self.sanitize(v) for v in data]
            return data
        except Exception as e:
            logger.error("Error during data structure sanitization: %s", e)
            return data


# Global singleton instance for easy import
_global_guard: OutputGuard | None = None


def get_output_guard() -> OutputGuard:
    """Retrieve or initialize the global output guard."""
    global _global_guard
    if _global_guard is None:
        _global_guard = OutputGuard()
    return _global_guard
