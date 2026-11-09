"""CLI command to create API keys with hashed/salted storage.

Purpose: Enforces SEC-20 and SEC-21:
         - Generates cryptographically secure API keys.
         - Stores only salted PBKDF2-HMAC-SHA256 hashes in database.
         - Shows the plaintext key exactly once.
"""

from __future__ import annotations

import argparse

from backend.api.auth import create_api_key
from backend.storage.database import get_db_session, get_engine, init_db


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a role-gated API key for the IIR platform."
    )
    parser.add_argument(
        "--role",
        choices=["viewer", "approver"],
        required=True,
        help="Access role assigned to the key ('viewer' or 'approver')",
    )
    parser.add_argument(
        "--label",
        required=True,
        help="Human-readable label or description for the key",
    )
    args = parser.parse_args()

    engine = get_engine()
    init_db(engine)

    session_gen = get_db_session(engine)
    session = next(session_gen)
    try:
        raw_key, record = create_api_key(session, label=args.label, role=args.role)
        print("=" * 60)
        print("API Key generated successfully!")
        print("=" * 60)
        print(f"ID:      {record.id}")
        print(f"Label:   {record.label}")
        print(f"Role:    {record.role}")
        print(f"Prefix:  {record.key_prefix}")
        print(f"API Key: {raw_key}")
        print("=" * 60)
        print("NOTICE: Store this key securely now. It will NEVER be shown again,")
        print("        and is stored only as a salted cryptographic hash.")
        print("=" * 60)
    finally:
        session.close()


if __name__ == "__main__":
    main()
