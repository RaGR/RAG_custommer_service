import os, sqlite3, faiss, numpy as np
from typing import List, Dict
from sentence_transformers import SentenceTransformer

class VectorSearcher:
    def __init__(self, db_path: str, index_dir: str, model_name: str):
        self.db_path = db_path
        self.index_path = os.path.join(index_dir, "index.faiss")
        self.meta_path = os.path.join(index_dir, "meta.npy")
        self.model = SentenceTransformer(model_name)
        self.index = faiss.read_index(self.index_path)
        self.ids = np.load(self.meta_path)

    def _conn(self):
        con = sqlite3.connect(self.db_path, check_same_thread=False)
        con.row_factory = sqlite3.Row
        return con

    def search(self, query: str, k: int = 5) -> List[Dict]:
        vec = self.model.encode([query], normalize_embeddings=True).astype("float32")
        scores, idxs = self.index.search(vec, k)
        idxs = idxs[0]
        hits = []
        with self._conn() as con:
            for pos, ii in enumerate(idxs):
                if ii < 0: 
                    continue
                row_id = int(self.ids[ii])
                row = con.execute(
                    "SELECT id, name, description, price FROM products WHERE id=?",
                    (row_id,)
                ).fetchone()
                if row:
                    hits.append({**dict(row), "rank": float(scores[0][pos])})
        return hits
