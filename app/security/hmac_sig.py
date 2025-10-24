"""HMAC signature verification for request integrity and replay protection."""

from __future__ import annotations

import hashlib
import hmac
import time
from collections import OrderedDict, defaultdict
from typing import DefaultDict

from fastapi import HTTPException, Request

from app.core.config import settings
from app.security.auth import AuthType, SecurityContext, unauthorized

_MAX_NONCES_PER_KEY = 256
_NONCE_CACHE: DefaultDict[str, OrderedDict[str, float]] = defaultdict(OrderedDict)


async def enforce_hmac(request: Request, context: SecurityContext) -> None:
    """Validate HMAC signature headers when enabled."""
    if not settings.hmac_required:
        return
    if context.auth_type is not AuthType.API_KEY or context.raw_api_key is None:
        # Only API key clients are expected to provide HMAC signatures.
        return

    signature = (request.headers.get("X-Signature") or "").strip().lower()
    timestamp = request.headers.get("X-Timestamp")
    nonce = (request.headers.get("X-Nonce") or "").strip()
    if not (signature and timestamp and nonce):
        raise unauthorized("hmac_missing_headers", "Missing HMAC headers")

    try:
        timestamp_int = int(timestamp)
    except ValueError as exc:
        raise unauthorized("hmac_bad_timestamp", "Invalid timestamp") from exc

    now = time.time()
    window = float(settings.hmac_window_sec)
    if abs(now - timestamp_int) > window:
        raise unauthorized("hmac_window_violation", "Signature timestamp outside permitted window")

    body_bytes = await request.body()
    body_digest = hashlib.sha256(body_bytes).hexdigest()
    canonical = f"{timestamp_int}.{nonce}.{request.method.upper()}.{request.url.path}.{body_digest}"
    expected = hmac.new(
        context.raw_api_key.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise unauthorized("hmac_mismatch", "Invalid HMAC signature")

    nonce_key = _nonce_cache_key(context)
    _record_nonce(nonce_key, nonce, now, window)


def _nonce_cache_key(context: SecurityContext) -> str:
    if context.api_key_id is not None:
        return f"key:{context.api_key_id}"
    digest = hashlib.sha256((context.raw_api_key or "").encode("utf-8")).hexdigest()
    return f"keyhash:{digest[:16]}"


def _record_nonce(cache_key: str, nonce: str, now: float, window: float) -> None:
    bucket = _NONCE_CACHE[cache_key]
    # Drop expired entries
    for existing_nonce, ts in list(bucket.items()):
        if now - ts > window:
            bucket.pop(existing_nonce, None)
    if nonce in bucket:
        raise unauthorized("hmac_replay", "Nonce already used")
    bucket[nonce] = now
    if len(bucket) > _MAX_NONCES_PER_KEY:
        bucket.popitem(last=False)
