import time
from typing import Dict, Tuple
from fastapi import Request, HTTPException
from app.core.config import settings

# identity -> (tokens, last_ts)
_BUCKETS: Dict[str, Tuple[float, float]] = {}

def _identity(req: Request) -> str:
    if settings.rl_identity_header.lower() == "ip":
        return req.client.host if req.client else "unknown"
    return req.headers.get(settings.rl_identity_header, req.client.host if req.client else "unknown")

async def rate_limit(request: Request):
    now = time.time()
    ident = _identity(request)
    bucket_size = settings.rl_bucket_size
    refill = settings.rl_refill_per_sec

    tokens, last = _BUCKETS.get(ident, (bucket_size, now))
    # refill
    tokens = min(bucket_size, tokens + (now - last) * refill)
    if tokens < 1.0:
        # 429 Too Many Requests
        raise HTTPException(status_code=429, detail="rate limit exceeded")
    _BUCKETS[ident] = (tokens - 1.0, now)
