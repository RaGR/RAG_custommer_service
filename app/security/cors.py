"""CORS configuration derived from application settings."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings


_ALLOWED_METHODS = ["GET", "POST", "OPTIONS"]
_ALLOWED_HEADERS = [
    "Authorization",
    "Content-Type",
    "X-API-Key",
    "X-Signature",
    "X-Timestamp",
    "X-Nonce",
]


def configure_cors(app: FastAPI) -> None:
    """Attach a restrictive CORS middleware using configured origins."""
    origins = settings.cors_origins or []
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=_ALLOWED_METHODS,
        allow_headers=_ALLOWED_HEADERS,
    )
