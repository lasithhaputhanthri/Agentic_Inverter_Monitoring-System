"""Security test to ensure plaintext API keys are never stored in the database.

Purpose: Verifies SEC-20 and Phase 6 acceptance test:
         - "The database file contains no plain API key (search for the generated key)."
"""

from __future__ import annotations

from pathlib import Path

from backend.api.auth import create_api_key
from backend.storage.database import get_session_factory, init_db
from sqlalchemy import create_engine


def test_database_contains_no_plaintext_keys(tmp_path: Path) -> None:
    db_file = tmp_path / "security_test.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    init_db(engine)

    session_factory = get_session_factory(engine)
    session = session_factory()

    generated_keys: list[str] = []

    try:
        # Generate several keys with different roles
        for i in range(5):
            role = "approver" if i % 2 == 0 else "viewer"
            raw_key, record = create_api_key(session, label=f"key-{i}", role=role)
            generated_keys.append(raw_key)

        session.commit()
    finally:
        session.close()
        engine.dispose()

    # Read all bytes from the database file and any journal/WAL files
    db_bytes = db_file.read_bytes()
    wal_file = tmp_path / "security_test.db-wal"
    wal_bytes = wal_file.read_bytes() if wal_file.exists() else b""

    combined_disk_bytes = db_bytes + wal_bytes

    # Search for each generated plaintext key in disk storage
    for raw_key in generated_keys:
        raw_bytes = raw_key.encode("utf-8")
        assert raw_bytes not in combined_disk_bytes, (
            f"CRITICAL SECURITY FAILURE: Plaintext API key {raw_key[:12]}... found on disk!"
        )

        # Also ensure significant sub-fragments (beyond the prefix) are absent
        secret_suffix = raw_key[10:]
        assert secret_suffix.encode("utf-8") not in combined_disk_bytes, (
            "CRITICAL: Secret key fragment discovered in database storage!"
        )
