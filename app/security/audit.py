"""Audit logging utilities and persistent security schema management."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

from app.core.config import settings

# SQLite pragmas tuned for small concurrent writes.
_PRAGMAS = (
    "PRAGMA journal_mode=WAL;",
    "PRAGMA synchronous=NORMAL;",
)


@contextmanager
def security_db(readonly: bool = False) -> Generator[sqlite3.Connection, None, None]:
    """Context manager that yields a SQLite connection to the security tables."""
    uri = settings.db_path
    conn = sqlite3.connect(
        uri,
        detect_types=sqlite3.PARSE_DECLTYPES,
        check_same_thread=False,
        isolation_level=None,
    )
    try:
        conn.row_factory = sqlite3.Row
        if not readonly:
            for pragma in _PRAGMAS:
                conn.execute(pragma)
        if not readonly:
            conn.execute("BEGIN")
        yield conn
        if not readonly:
            conn.commit()
    except Exception:
        if not readonly:
            conn.rollback()
        raise
    finally:
        conn.close()


def init_security_tables() -> None:
    """Ensure security-related tables exist."""
    with security_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                key_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_used_at DATETIME
            );

            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                path TEXT NOT NULL,
                status TEXT NOT NULL,
                note TEXT
            );

            CREATE TABLE IF NOT EXISTS tenant_limits (
                tenant_id TEXT PRIMARY KEY,
                bucket INTEGER NOT NULL,
                refill REAL NOT NULL
            );
            """
        )


def audit_event(actor: str, action: str, path: str, status: str, note: str | None = None) -> None:
    """Persist a structured audit trail entry for privileged actions."""
    now = datetime.utcnow().isoformat(timespec="seconds")
    with security_db() as conn:
        conn.execute(
            """
            INSERT INTO audit(actor, action, path, status, note, ts)
            VALUES(?,?,?,?,?,?)
            """,
            (actor, action, path, status, note, now),
        )
