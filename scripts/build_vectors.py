#!/usr/bin/env python3
"""
Build a FAISS vector index from SQLite products table (CPU-only, Persian-friendly).

Reads:
  - SQLite DB:   env DB_PATH (default: rag-instabot/db/app_data.sqlite)
  - Table:       products(id INTEGER PK, name TEXT, description TEXT, price REAL)

Writes:
  - INDEX_PATH/index.faiss   (FAISS index with normalized embeddings)
  - INDEX_PATH/meta.npy      (numpy int32 array of row ids aligned with the index)

Environment vars you can override:
  DB_PATH=rag-instabot/db/app_data.sqlite
  INDEX_PATH=rag-instabot/data/faiss_index
  EMBED_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
  BATCH_SIZE=32
"""

import os
os.environ["CUDA_VISIBLE_DEVICES"] = ""  # Hard-disable GPUs for this process

import sys
import sqlite3
import numpy as np

# Torch must be imported after forcing CPU visibility above
import torch  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402
import faiss  # noqa: E402


# ---------- Config ----------
DB_PATH     = os.getenv("DB_PATH", "/home/ragr/Desktop/rag-instabot/db/app_data.sqlite")
INDEX_PATH  = os.getenv("INDEX_PATH", "/home/ragr/Desktop/rag-instabot/data/faiss_index")
MODEL_NAME  = os.getenv("EMBED_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
BATCH_SIZE  = int(os.getenv("BATCH_SIZE", "32"))

# Ensure CPU-only run
if torch.cuda.is_available():
    print("[warn] CUDA is visible but will be ignored. Forcing CPU.", file=sys.stderr)
device = "cpu"
torch.set_num_threads(max(1, os.cpu_count() or 1))

# ---------- Helpers ----------
def fail(msg: str):
    print(f"[error] {msg}", file=sys.stderr)
    sys.exit(1)

def ensure_paths():
    if not os.path.exists(DB_PATH):
        fail(f"SQLite DB not found at: {DB_PATH}")
    os.makedirs(INDEX_PATH, exist_ok=True)

def load_rows():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    try:
        cur.execute("SELECT id, name, description FROM products ORDER BY id")
        rows = cur.fetchall()
    finally:
        con.close()

    if not rows:
        fail("No rows found in products. Ensure the DB is populated.")
    return rows

def build_texts(rows):
    docs, ids = [], []
    for _id, name, desc in rows:
        name = (name or "").strip()
        desc = (desc or "").strip()
        text = f"{name} - {desc}".strip(" -")
        if not text:
            # skip totally empty rows
            continue
        docs.append(text)
        ids.append(int(_id))
    if not docs:
        fail("All rows were empty after cleaning. Check your data.")
    return docs, np.array(ids, dtype=np.int32)

# ---------- Main ----------
def main():
    ensure_paths()
    rows = load_rows()
    docs, ids = build_texts(rows)

    print(f"[info] rows read: {len(rows)} | docs to embed: {len(docs)}")
    print(f"[info] model: {MODEL_NAME} | batch_size: {BATCH_SIZE} | device: {device}")

    # Load embedding model (CPU)
    model = SentenceTransformer(MODEL_NAME, device=device)

    # Encode in batches on CPU; normalize for cosine via inner product
    embeddings = model.encode(
        docs,
        batch_size=BATCH_SIZE,
        show_progress_bar=True,
        normalize_embeddings=True,
        device=device,
    )
    emb = np.asarray(embeddings, dtype="float32")
    if emb.ndim != 2 or emb.shape[0] != len(ids):
        fail("Embedding shape mismatch with ids.")

    d = emb.shape[1]
    print(f"[info] embedding matrix shape: {emb.shape} (dim={d})")

    # Build FAISS index (inner product; cosine since vectors are normalized)
    index = faiss.IndexFlatIP(d)
    index.add(emb)

    # Save index + metadata
    idx_path  = os.path.join(INDEX_PATH, "index.faiss")
    meta_path = os.path.join(INDEX_PATH, "meta.npy")
    faiss.write_index(index, idx_path)
    np.save(meta_path, ids)

    print(f"[ok] vectors indexed: {len(ids)}")
    print(f"[ok] index saved to: {idx_path}")
    print(f"[ok] metadata saved to: {meta_path}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        fail(str(e))
