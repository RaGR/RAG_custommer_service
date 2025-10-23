from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Dict
from app.retrieval.normalize import normalize_query
from app.retrieval.fts import connect, search_fts
from app.retrieval.vector import VectorSearcher
from app.retrieval.score import filter_by_threshold, merge_unique
from app.prompting.builder import build_prompt
from app.llm.client import ask_llm
from app.core.config import settings
from app.security.auth import enforce_api_key
from app.security.rate_limit import rate_limit
import os, sqlite3, time

DB_PATH = settings.db_path
INDEX_PATH = settings.index_path
EMBED_MODEL = settings.embed_model
VEC = VectorSearcher(DB_PATH, INDEX_PATH, EMBED_MODEL)

router = APIRouter(prefix="", tags=["dm"])

class DMIn(BaseModel):
    sender_id: str = Field(..., max_length=64)
    message_id: str = Field(..., max_length=64)
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
    await enforce_api_key(request)
    await rate_limit(request)

    q0 = payload.text
    q = normalize_query(q0)
    if not q:
        raise HTTPException(status_code=400, detail="empty text")

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
    # Minimal safe log
    print({
        "path": "/simulate_dm", "latency_ms": dt,
        "q_len": len(q0), "hits": len(retrieved),
        "provider": settings.llm_provider
    })

    return DMOut(reply=answer)

# Feedback endpoint
class FeedbackIn(BaseModel):
    message_id: str
    rating: str
    note: str | None = None

@router.post("/feedback")
async def feedback(payload: FeedbackIn, request: Request):
    await enforce_api_key(request)
    await rate_limit(request)
    con = sqlite3.connect(DB_PATH)
    con.execute("INSERT INTO feedback(message_id, rating, note) VALUES (?,?,?)",
                (payload.message_id, payload.rating[:16], (payload.note or "")[:500]))
    con.commit(); con.close()
    return {"ok": True}
