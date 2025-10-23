from typing import List, Dict
from app.core.config import settings

def filter_by_threshold(vec_hits: List[Dict]) -> List[Dict]:
    th = settings.min_vector_score
    out = []
    for h in vec_hits:
        # rank holds IP score (higher better)
        score = float(h.get("rank", 0))
        if score >= th:
            out.append(h)
    return out

def merge_unique(primary: List[Dict], secondary: List[Dict], k: int) -> List[Dict]:
    seen, out = set(), []
    for it in primary + secondary:
        iid = it.get("id")
        if iid in seen:
            continue
        seen.add(iid)
        out.append(it)
        if len(out) >= k:
            break
    return out
