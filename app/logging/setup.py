"""Logging helpers to produce structured, privacy-safe output."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from hashlib import blake2b
from typing import Any, Dict

from app.core.config import settings


class JsonFormatter(logging.Formatter):
    """Render log records as compact JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        if record.args and isinstance(record.args, dict):
            payload.update(record.args)
        for field in ("request_id", "path", "method", "status", "latency_ms", "identity", "roles", "rl_tokens", "provider", "llm_ms"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def setup_logging() -> None:
    """Configure root logging handlers."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(handler)


def hash_identity(identity: str) -> str:
    """Produce an irreversible hash for logging identities."""
    digest = blake2b(identity.encode("utf-8"), digest_size=8)
    return digest.hexdigest()
