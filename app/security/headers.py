"""Security middleware for response headers and request body limits."""

from __future__ import annotations

from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import Message

from app.core.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach standard security headers to every response."""

    def __init__(self, app):
        super().__init__(app)
        self._headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "interest-cohort=()",
            "Content-Security-Policy": (
                "default-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self'"
            ),
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response: Response = await call_next(request)
        if settings.security_headers_enabled:
            for header, value in self._headers.items():
                response.headers.setdefault(header, value)
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Ensure incoming request bodies do not exceed configured maximum."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        limit = int(settings.max_request_body_bytes)
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > limit:
                    return _payload_too_large_response()
            except ValueError:
                # ignore malformed header; enforce after reading body
                pass

        body = await request.body()
        if len(body) > limit:
            return _payload_too_large_response()

        body_consumed = False

        async def receive() -> Message:
            nonlocal body_consumed
            if not body_consumed:
                body_consumed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.request", "body": b"", "more_body": False}

        # Ensure downstream consumers can re-read the buffered body.
        request._receive = receive  # type: ignore[attr-defined]
        request._body = body  # type: ignore[attr-defined]

        return await call_next(request)


def _payload_too_large_response() -> Response:
    return JSONResponse(
        status_code=413,
        content={
            "detail": {
                "code": "payload_too_large",
                "detail": "Request body exceeds configured limit",
            }
        },
    )
