"""Admin endpoints for API key lifecycle management."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.security.auth import (
    Role,
    create_api_key,
    disable_api_key,
    enable_api_key,
    list_api_keys,
    require_roles,
)

router = APIRouter(prefix="/admin", tags=["admin"])


class CreateKeyRequest(BaseModel):
    name: str = Field(..., max_length=64)
    role: Role


class CreateKeyResponse(BaseModel):
    api_key: str
    id: int
    role: Role
    name: str


@router.get("/api-keys")
async def list_keys(request: Request):
    await require_roles(request, (Role.ADMIN,))
    return {"items": list_api_keys(include_disabled=True)}


@router.post("/api-keys", response_model=CreateKeyResponse)
async def create_key(payload: CreateKeyRequest, request: Request):
    await require_roles(request, (Role.ADMIN,))
    key_plain, record = create_api_key(payload.name, payload.role)
    return CreateKeyResponse(api_key=key_plain, id=record.id, role=record.role, name=record.name)


@router.post("/api-keys/{key_id}/disable")
async def disable_key(key_id: int, request: Request):
    await require_roles(request, (Role.ADMIN,))
    disable_api_key(key_id)
    return {"ok": True}


@router.post("/api-keys/{key_id}/enable")
async def enable_key_endpoint(key_id: int, request: Request):
    await require_roles(request, (Role.ADMIN,))
    enable_api_key(key_id)
    return {"ok": True}
