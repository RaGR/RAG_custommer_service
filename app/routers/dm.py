from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.retrieval.normalize import normalize_query
from app.retrieval.fts import connect, search_fts
from app.prompting.builder import build_prompt
from app.llm.client import ask_llm
from app.core.config import settings

# NEW imports:
import os
from app.retrieval.vector import VectorSearcher

DB_PATH = os.getenv("DB_PATH", "/home/ragr/Desktop/rag-instabot/db/app_data.sqlite")
INDEX_PATH = os.getenv("INDEX_PATH", "/home/ragr/Desktop/rag-instabot/data/faiss_index")
EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

# Lazy-initialize vector searcher (at import time is fine for a single process)
VEC = VectorSearcher(DB_PATH, INDEX_PATH, EMBED_MODEL)

router = APIRouter(prefix="", tags=["dm"])

class DMIn(BaseModel):
    sender_id: str = Field(..., max_length=64)
    message_id: str = Field(..., max_length=64)
    text: str = Field(..., max_length=500)

class DMOut(BaseModel):
    reply: str

def merge_unique(primary, secondary, k=5):
    seen = set()
    out = []
    for item in primary + secondary:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        out.append(item)
        if len(out) >= k:
            break
    return out

@router.post("/simulate_dm", response_model=DMOut)
async def simulate_dm(payload: DMIn):
    q = normalize_query(payload.text)
    if not q:
        raise HTTPException(status_code=400, detail="empty text")

    # Vector first (semantic), fallback to FTS, then merge
    vec_hits = VEC.search(q, k=5)
    with connect(DB_PATH) as conn:
        fts_hits = search_fts(conn, q, k=5)

    retrieved = merge_unique(vec_hits, fts_hits, k=4)

    prompt = build_prompt(q, retrieved)
    answer = await ask_llm(prompt)
    return DMOut(reply=answer)
