"""FastAPI application factory and middleware configuration.

Purpose: Enforces SEC-08, SEC-10, SEC-11, SEC-12, Rule 40, and Rule 50.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine

from backend.api.middleware import (
    BodySizeLimitMiddleware,
    OutputGuardMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    register_exception_handlers,
)
from backend.api.routes import router as api_v1_router
from backend.storage.database import get_engine, init_db

# Explicit CORS allowlist (SEC-11)
DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:8501",  # Streamlit default port
    "http://127.0.0.1:8501",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]


def create_app(engine: Engine | None = None) -> FastAPI:
    """Create and configure FastAPI instance with security middlewares and routes."""
    app_env = os.getenv("APP_ENV", "development").lower()

    # SEC-12: Disable OpenAPI interactive documentation in production
    is_production = app_env == "production"
    docs_url = None if is_production else "/docs"
    redoc_url = None if is_production else "/redoc"
    openapi_url = None if is_production else "/openapi.json"

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        # Application startup
        db_engine = engine or get_engine()
        app.state.engine = db_engine
        init_db(db_engine)
        yield
        # Application shutdown
        db_engine.dispose()

    app = FastAPI(
        title="IoT Inverter Incident Response API",
        version="1.0.0",
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )

    # Attach db engine to app state immediately
    if engine is not None:
        app.state.engine = engine

    # Register SEC-08 exception handlers
    register_exception_handlers(app)

    # SEC-11: Explicit CORS configuration
    cors_origins_env = os.getenv("ALLOWED_ORIGINS")
    allowed_origins = (
        [o.strip() for o in cors_origins_env.split(",") if o.strip()]
        if cors_origins_env
        else DEFAULT_ALLOWED_ORIGINS
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["X-API-Key", "Content-Type", "X-Request-ID"],
    )

    # Middleware execution chain (in reverse order of addition):
    # 1. OutputGuardMiddleware (sanitizes response outgoing text)
    # 2. RateLimitMiddleware (enforces 60 req/min per key)
    # 3. BodySizeLimitMiddleware (enforces 16 KB max body)
    # 4. SecurityHeadersMiddleware (attaches SEC-10 headers & request ID)
    app.add_middleware(OutputGuardMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    # Include API routes
    app.include_router(api_v1_router)

    return app


# Default app instance
app = create_app()
