"""Configurable token bucket rate limiting with tenant overrides."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import DefaultDict, Optional, Tuple

from fastapi import HTTPException, Request

from app.core.config import settings
from app.security.audit import security_db
from app.security.auth import Role, SecurityContext


@dataclass(slots=True)
class BucketConfig:
    capacity: float
    refill_rate: float


@dataclass(slots=True)
class BucketState:
    tokens: float
    last_refill_ts: float

_BUCKETS: dict[str, BucketState] = {}
_TENANT_CACHE: dict[str, Tuple[BucketConfig, float]] = {}
_TENANT_CACHE_TTL = 60.0

ratelimit_block_total = 0


def _retry_error(retry_after: float) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail={"code": "rate_limited", "detail": "Rate limit exceeded"},
        headers={"Retry-After": f"{max(1, int(retry_after))}"},
    )


def _identity(request: Request, context: Optional[SecurityContext]) -> str:
    if context:
        return context.subject
    if settings.rl_identity_header.lower() == "ip":
        host = request.client.host if request.client else "unknown"
        return f"ip:{host}"
    header_name = settings.rl_identity_header
    value = request.headers.get(header_name)
    if value:
        return f"hdr:{value}"
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"


def _default_bucket() -> BucketConfig:
    return BucketConfig(
        capacity=float(settings.rl_bucket_size),
        refill_rate=float(settings.rl_refill_per_sec),
    )


def _load_tenant_limit(identity: str) -> BucketConfig:
    now = time.monotonic()
    cached = _TENANT_CACHE.get(identity)
    if cached and now - cached[1] < _TENANT_CACHE_TTL:
        return cached[0]

    with security_db(readonly=True) as conn:
        row = conn.execute(
            "SELECT bucket, refill FROM tenant_limits WHERE tenant_id = ?",
            (identity,),
        ).fetchone()

    if row:
        config = BucketConfig(capacity=float(row["bucket"]), refill_rate=float(row["refill"]))
        _TENANT_CACHE[identity] = (config, now)
        return config

    config = _default_bucket()
    _TENANT_CACHE[identity] = (config, now)
    return config


async def enforce_rate_limit(request: Request, context: Optional[SecurityContext]) -> None:
    """Apply token bucket rate limiting using identity derived from request context."""
    global ratelimit_block_total

    identity = _identity(request, context)
    config = _load_tenant_limit(identity)
    state = _BUCKETS.get(identity)
    now = time.monotonic()

    if state is None:
        state = BucketState(tokens=config.capacity, last_refill_ts=now)

    elapsed = max(0.0, now - state.last_refill_ts)
    state.tokens = min(config.capacity, state.tokens + elapsed * config.refill_rate)
    state.last_refill_ts = now

    if state.tokens < 1.0:
        ratelimit_block_total += 1
        retry_after = (1.0 - state.tokens) / config.refill_rate if config.refill_rate else 1.0
        _BUCKETS[identity] = state
        raise _retry_error(retry_after)

    state.tokens -= 1.0
    _BUCKETS[identity] = state
    request.state.rate_limit_tokens = state.tokens  # type: ignore[attr-defined]
