"""Input normalization utilities for Persian language queries."""

from __future__ import annotations

import re
import unicodedata

_CTRL_RE = re.compile(r"[\u0000-\u001F\u007F]")
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_SCRIPT_RE = re.compile(r"<\s*script.*?>.*?<\s*/\s*script\s*>", re.IGNORECASE | re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]+>")

_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def normalize_query(txt: str) -> str:
    """Normalize Persian text for retrieval queries."""
    if not txt:
        return ""
    text = unicodedata.normalize("NFC", txt)
    text = text.translate(_DIGIT_MAP)
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = _CTRL_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def sanitize_text(value: str, max_length: int) -> str:
    """Strip URLs, HTML, and risky characters before prompt construction."""
    if not value:
        return ""
    text = unicodedata.normalize("NFC", value)
    text = text.translate(_DIGIT_MAP)
    text = _SCRIPT_RE.sub("", text)
    text = _URL_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    text = text.replace("\u200c", " ")
    text = _CTRL_RE.sub(" ", text)
    text = re.sub(r"[<>`$]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_length]
