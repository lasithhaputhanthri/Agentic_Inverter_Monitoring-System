"""Authentication and API key management layer.

Purpose: Enforces SEC-20, SEC-21, and SEC-71:
         - Keys generated via secrets.token_urlsafe(32).
         - Stored exclusively as salted PBKDF2-HMAC-SHA256 hashes.
         - Lookup by 8-character prefix, verified with hmac.compare_digest.
         - Log failed authentication with key prefix and source only. Never log full key.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from typing import Literal

from sqlalchemy.orm import Session

from backend.storage.models import ApiKeyRecord
from backend.storage.repositories import ApiKeyRepository

logger = logging.getLogger(__name__)

PREFIX_LENGTH = 8
SALT_BYTES = 16
PBKDF2_ITERATIONS = 100_000
ALLOWED_ROLES = {"viewer", "approver"}


def hash_key(raw_key: str, salt_hex: str) -> str:
    """Derive cryptographic hash for an API key using PBKDF2-HMAC-SHA256."""
    salt = bytes.fromhex(salt_hex)
    derived = hashlib.pbkdf2_hmac("sha256", raw_key.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return derived.hex()


def create_api_key(
    session: Session,
    label: str,
    role: Literal["viewer", "approver"] | str,
) -> tuple[str, ApiKeyRecord]:
    """Generate a new API key, store its salted hash, and return the plaintext key once."""
    if role not in ALLOWED_ROLES:
        raise ValueError(f"Invalid role '{role}'. Allowed roles are: {sorted(ALLOWED_ROLES)}")

    raw_token = secrets.token_urlsafe(32)
    prefix = raw_token[:PREFIX_LENGTH]
    salt_hex = secrets.token_hex(SALT_BYTES)
    key_hash = hash_key(raw_token, salt_hex)

    repo = ApiKeyRepository(session)
    record = repo.create_key(
        label=label,
        role=role,
        key_hash=key_hash,
        key_prefix=prefix,
        salt=salt_hex,
    )
    return raw_token, record


def verify_api_key(
    session: Session,
    raw_key: str | None,
    client_source: str = "unknown",
) -> ApiKeyRecord | None:
    """Verify an API key by prefix lookup and constant-time hash comparison."""
    if not raw_key or len(raw_key) < PREFIX_LENGTH:
        logger.warning(
            "Authentication failed: missing or malformed key from source %s",
            client_source,
        )
        return None

    prefix = raw_key[:PREFIX_LENGTH]
    repo = ApiKeyRepository(session)
    candidates = repo.get_by_prefix(prefix)

    if not candidates:
        logger.warning(
            "Authentication failed: unknown key prefix '%s' from source %s",
            prefix,
            client_source,
        )
        return None

    for candidate in candidates:
        computed_hash = hash_key(raw_key, candidate.salt)
        if hmac.compare_digest(computed_hash, candidate.key_hash):
            if candidate.revoked_at is not None:
                logger.warning(
                    "Authentication failed: revoked key prefix '%s' from source %s",
                    prefix,
                    client_source,
                )
                return None
            return candidate

    logger.warning(
        "Authentication failed: hash mismatch for key prefix '%s' from source %s",
        prefix,
        client_source,
    )
    return None
