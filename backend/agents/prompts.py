"""Prompt loading and cryptographic hash verification.

Purpose: Loads versioned prompt templates from disk and computes SHA-256 integrity hashes.
Inputs: Prompt template filename or identifier.
Outputs: Loaded prompt text and SHA-256 hex digest.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"


@lru_cache(maxsize=16)
def load_prompt(filename: str) -> tuple[str, str]:
    """Load a prompt template from disk and compute its SHA-256 hash.

    Args:
        filename: Name of the prompt file (e.g. 'diagnosis_v1.txt').

    Returns:
        Tuple of (prompt_text, sha256_hex_hash).
    """
    path = PROMPTS_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"Prompt template file not found: {path}")

    content = path.read_text(encoding="utf-8")
    hasher = hashlib.sha256()
    hasher.update(content.encode("utf-8"))
    sha256_hash = hasher.hexdigest()

    return content, sha256_hash
