import os, sqlite3, faiss, numpy as np
from sentence_transformers import SentenceTransformer

DB = "/home/ragr/Desktop/rag-instabot/db/app_data.sqlite"
INDEX_DIR = os.getenv("INDEX_PATH", "rag-instabot/data/faiss_index")
MODEL_NAME = os.getenv("EMBED_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

os.makedirs(INDEX_DIR, exist_ok=True)
idx_path = os.path.join(INDEX_DIR, "index.faiss")
meta_path = os.path.join(INDEX_DIR, "meta.npy")

# 1) read data
con = sqlite3.connect(DB)
cur = con.cursor()
rows = cur.execute("SELECT id, name, description FROM products ORDER BY id").fetchall()
con.close()

docs = []
ids = []
for _id, name, desc in rows:
    text = f"{name} - {desc}".strip()
    docs.append(text)
    ids.append(_id)

# 2) embed
model = SentenceTransformer(MODEL_NAME)
emb = model.encode(docs, show_progress_bar=True, normalize_embeddings=True)
emb = np.array(emb).astype("float32")

# 3) build faiss
d = emb.shape[1]
index = faiss.IndexFlatIP(d)  # cosine via normalized vectors
index.add(emb)

# 4) save
faiss.write_index(index, idx_path)
np.save(meta_path, np.array(ids, dtype=np.int32))
print(f"OK: vectors={len(ids)} dim={d} → {idx_path}")
