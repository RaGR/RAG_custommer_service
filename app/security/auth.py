from fastapi import Request, HTTPException
from app.core.config import settings

async def enforce_api_key(request: Request):
    if not settings.require_api_key:
        return
    key = request.headers.get("X-API-Key", "")
    if not key or key != settings.api_key:
        raise HTTPException(status_code=401, detail="unauthorized")
