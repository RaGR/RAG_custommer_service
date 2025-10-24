"""Routers responsible for DM simulation and feedback submission."""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from typing import Dict, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import settings
from app.llm.client import ask_llm
from app.prompting.builder import build_prompt
from app.retrieval.fts import connect, search_fts
from app.retrieval.normalize import normalize_query, sanitize_text
from app.retrieval.score import filter_by_threshold, merge_unique
from app.retrieval.vector import VectorSearcher
from app.security.auth import Role, require_roles
from app.security.hmac_sig import enforce_hmac
from app.security.rate_limit import enforce_rate_limit

logger = logging.getLogger("app.dm")

DB_PATH = settings.db_path
INDEX_PATH = settings.index_path
EMBED_MODEL = settings.embed_model
VEC = VectorSearcher(DB_PATH, INDEX_PATH, EMBED_MODEL)

router = APIRouter(prefix="", tags=["dm"])

class DMIn(BaseModel):
    sender_id: str = Field(..., max_length=64, pattern=r"^[A-Za-z0-9_\-:.]{1,64}$")
    message_id: str = Field(..., max_length=64, pattern=r"^[A-Za-z0-9_\-:.]{1,64}$")
    text: str = Field(..., max_length=500)

class DMOut(BaseModel):
    reply: str

def _feedback_table_init():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id TEXT, rating TEXT, note TEXT, ts DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    con.commit(); con.close()

_feedback_table_init()

@router.post("/simulate_dm", response_model=DMOut)
async def simulate_dm(payload: DMIn, request: Request):
    context = await require_roles(request, (Role.CLIENT, Role.ANALYST, Role.ADMIN))
    await enforce_hmac(request, context)
    await enforce_rate_limit(request, context)

    q0 = payload.text
    q = normalize_query(q0)
    if not q:
        raise HTTPException(status_code=400, detail={"code": "empty_text", "detail": "Empty text"})

    t0 = time.time()

    # Vector retrieval + threshold
    vec_hits = VEC.search(q, k=8)
    vec_hits = filter_by_threshold(vec_hits)

    # FTS retrieval
    with connect(DB_PATH) as conn:
        fts_hits = search_fts(conn, q, k=6)

    # Merge & cap
    retrieved = merge_unique(vec_hits, fts_hits, k=settings.max_ctx_items)

    # Build prompt + LLM
    prompt = build_prompt(q, retrieved)
    answer = await ask_llm(prompt)

    dt = int((time.time() - t0) * 1000)
    logger.info(
        "simulate_dm",
        extra={
            "latency_ms": dt,
            "hits": len(retrieved),
            "provider": settings.llm_provider,
            "q_len": len(q0),
        },
    )

    return DMOut(reply=answer)

# Feedback endpoint
class FeedbackIn(BaseModel):
    message_id: str = Field(..., max_length=64, pattern=r"^[A-Za-z0-9_\-:.]{1,64}$")
    rating: str = Field(..., max_length=16, pattern=r"^[A-Za-z0-9_\-]+$")
    note: str | None = Field(default=None, max_length=500)

@router.post("/feedback")
async def feedback(payload: FeedbackIn, request: Request):
    context = await require_roles(request, (Role.CLIENT, Role.ANALYST, Role.ADMIN))
    await enforce_hmac(request, context)
    await enforce_rate_limit(request, context)

    note_clean = sanitize_text(payload.note or "", 500)
    try:
        con = sqlite3.connect(DB_PATH)
        con.execute(
            "INSERT INTO feedback(message_id, rating, note) VALUES (?,?,?)",
            (payload.message_id, payload.rating[:16], note_clean),
        )
        con.commit()
    except sqlite3.DatabaseError as exc:
        raise HTTPException(status_code=500, detail={"code": "db_error", "detail": "Failed to persist feedback"}) from exc
    finally:
        con.close()
    return {"ok": True}
