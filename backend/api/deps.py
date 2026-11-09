"""FastAPI dependency injection layer.

Purpose: Enforces SEC-21:
         - Role checks ('viewer', 'approver') live strictly in this layer.
         - DB session life-cycle management.
         - Extraction and verification of X-API-Key header.
"""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.api.auth import verify_api_key
from backend.storage.database import get_db_session, get_engine
from backend.storage.models import ApiKeyRecord


def get_db(request: Request) -> Generator[Session, None, None]:
    """Provide scoped database session from application state or engine."""
    engine = getattr(request.app.state, "engine", None)
    if engine is None:
        engine = get_engine()
    yield from get_db_session(engine)


def get_current_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    session: Session = Depends(get_db),
) -> ApiKeyRecord:
    """Extract and authenticate API key from HTTP header."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required X-API-Key header",
        )

    client_host = request.client.host if request.client else "unknown"
    key_record = verify_api_key(session, x_api_key, client_source=client_host)
    if key_record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
        )

    # Attach key record to request state for downstream middlewares (e.g. rate limiter)
    request.state.api_key = key_record
    return key_record


def require_viewer(
    key: ApiKeyRecord = Depends(get_current_api_key),
) -> ApiKeyRecord:
    """Authorize access for viewers and approvers."""
    if key.role not in ("viewer", "approver"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: viewer or approver role required",
        )
    return key


def require_approver(
    key: ApiKeyRecord = Depends(get_current_api_key),
) -> ApiKeyRecord:
    """Authorize access strictly for approvers."""
    if key.role != "approver":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: approver role required",
        )
    return key
