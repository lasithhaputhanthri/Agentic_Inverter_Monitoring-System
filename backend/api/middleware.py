"""Security and operational middleware for FastAPI.

Purpose: Enforces SEC-08, SEC-10, SEC-11, Rule 40 (limits), and Rule 50 (output guard):
         - Generic error handler returning request IDs without leaking stack traces.
         - Security headers on every response (nosniff, frame-options, HSTS, CSP, referrer).
         - Max 16 KB request body enforcement (HTTP 413).
         - Rate limiter per client/API key (60 req/min -> HTTP 429 with Retry-After).
         - Output guard sanitizing outgoing JSON payloads.
"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from backend.guard.output_guard import get_output_guard
from backend.limits.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 16 * 1024  # 16 KB


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add SEC-10 security headers and trace request IDs to every response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = request_id

        response: Response = await call_next(request)

        # SEC-10 Security Headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Request-ID"] = request_id

        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject request bodies exceeding 16 KB with HTTP 413 (Rule 40)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_BODY_BYTES:
                    return JSONResponse(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        content={
                            "detail": f"Request body exceeds maximum limit of {MAX_BODY_BYTES} bytes"
                        },
                    )
            except ValueError:
                pass

        # For streamed requests without content-length or to verify stream
        body = await request.body()
        if len(body) > MAX_BODY_BYTES:
            return JSONResponse(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                content={"detail": f"Request body exceeds maximum limit of {MAX_BODY_BYTES} bytes"},
            )

        resp: Response = await call_next(request)
        return resp


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Enforce 60 requests per minute per API key or client IP (Rule 40)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Exclude health check from strict rate limits if needed, or apply globally
        key = request.headers.get("X-API-Key")
        if not key:
            key = request.client.host if request.client else "anonymous"
        else:
            # Use prefix to track
            key = key[:8]

        limiter = get_rate_limiter()
        allowed, retry_after = limiter.check_rate_limit(key)
        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Too many requests. Rate limit of 60 req/min exceeded."},
                headers={"Retry-After": str(retry_after)},
            )

        resp: Response = await call_next(request)
        return resp


class OutputGuardMiddleware(BaseHTTPMiddleware):
    """Sanitize all outgoing JSON text responses via OutputGuard (Rule 50)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response: Response = await call_next(request)

        # Only process JSON responses
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type and hasattr(response, "body_iterator"):
            body_bytes = b"".join([chunk async for chunk in response.body_iterator])
            try:
                text = body_bytes.decode("utf-8")
                data = json.loads(text)
                guard = get_output_guard()
                sanitized_data = guard.sanitize(data)
                new_body = json.dumps(sanitized_data).encode("utf-8")

                # Build replacement response
                headers = dict(response.headers)
                headers["content-length"] = str(len(new_body))
                return Response(
                    content=new_body,
                    status_code=response.status_code,
                    headers=headers,
                    media_type="application/json",
                )
            except Exception as e:
                logger.error("Error sanitizing response payload: %s", e)
                return Response(
                    content=body_bytes,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )

        return response


def register_exception_handlers(app: FastAPI) -> None:
    """Register SEC-08 generic exception handlers hiding internal tracebacks."""

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
        logger.error(
            "Unhandled server error [request_id=%s] on %s %s: %s",
            request_id,
            request.method,
            request.url.path,
            exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal server error",
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )
