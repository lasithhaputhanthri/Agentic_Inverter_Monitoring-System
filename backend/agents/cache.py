"""Deterministic cache for LLM agent inference.

Purpose: Avoids redundant inference calls for identical incident signatures and prompt versions.
Inputs: Feature dictionary or string, prompt version identifier, and model name.
Outputs: Cached result object or None.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


class AgentCache:
    """In-memory cache keyed by features hash, prompt version, and model name."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def _make_key(self, features: dict[str, Any] | str, prompt_version: str, model: str) -> str:
        """Derive deterministic SHA-256 cache key."""
        if isinstance(features, dict):
            feat_repr = json.dumps(features, sort_keys=True)
        else:
            feat_repr = str(features)

        composite = f"{feat_repr}|{prompt_version}|{model}"
        return hashlib.sha256(composite.encode("utf-8")).hexdigest()

    def get(self, features: dict[str, Any] | str, prompt_version: str, model: str) -> Any | None:
        """Lookup cached inference result."""
        key = self._make_key(features, prompt_version, model)
        return self._store.get(key)

    def set(
        self, features: dict[str, Any] | str, prompt_version: str, model: str, value: Any
    ) -> None:
        """Store inference result in cache."""
        key = self._make_key(features, prompt_version, model)
        self._store[key] = value

    def clear(self) -> None:
        """Clear all cached entries."""
        self._store.clear()
