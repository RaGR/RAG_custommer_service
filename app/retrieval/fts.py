import sqlite3
from typing import List, Dict

def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def search_fallback_like(conn, q: str, k: int = 5):
    tokens = [t for t in q.split() if len(t) >= 2]
    if not tokens:
        return []
    pattern = "%" + "%".join(tokens) + "%"
    sql = """
    SELECT id, name, description, price
    FROM products
    WHERE name LIKE ? OR description LIKE ?
    LIMIT ?;
    """
    rows = conn.execute(sql, (pattern, pattern, k)).fetchall()
    return [dict(r) for r in rows]

def search_fts(conn: sqlite3.Connection, q: str, k: int = 5) -> List[Dict]:
    tokens = [t for t in q.split() if t]
    if not tokens:
        return []
    fts_expr = " OR ".join(f'"{t}"' for t in tokens)
    sql = """
    SELECT p.id, p.name, p.description, p.price, bm25(products_fts) AS rank
    FROM products_fts
    JOIN products p ON p.id = products_fts.rowid
    WHERE products_fts MATCH ?
    ORDER BY rank ASC
    LIMIT ?;
    """
    rows = conn.execute(sql, (fts_expr, k)).fetchall()
    results = [dict(r) for r in rows]
    if not results:
        results = search_fallback_like(conn, q, k)
    return results
