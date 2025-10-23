import httpx
import os
import re
import urllib.parse
from typing import Optional
from app.core.config import settings

async def ask_llm(prompt: str) -> str:
    provider = settings.llm_provider.lower().strip()
    if provider == "openrouter":
        return await _call_openrouter(prompt)
    else:
        # Safe local fallback (no external call)
        # Extract a brief answer-ish summary: if no data, say unknown.
        if "داده‌های مرتبط:\n—" in prompt:
            return "اطلاعات کافی در دیتابیس موجود نیست."
        # Otherwise, generic concise acknowledgment (RAG-only result)
        return "براساس داده‌های موجود، این گزینه‌ها مناسب‌اند. اگر مورد خاصی مدنظر دارید دقیق‌تر بفرمایید."

_ASCII_RE = re.compile(r"[^\x20-\x7E]")  # visible ASCII per RFC

def _ascii_or_none(value: str | None, max_len: int = 256) -> str | None:
    """Return ASCII-only header value or None if empty after sanitization."""
    if not value:
        return None
    # Strip leading/trailing spaces and remove non-ASCII bytes
    clean = _ASCII_RE.sub("", value.strip())
    if not clean:
        return None
    return clean[:max_len]

def _safe_openrouter_headers() -> dict:
    """
    Build OpenRouter headers with ASCII-only values.
    - Authorization MUST be ASCII (Bearer <key>).
    - HTTP-Referer and X-Title are optional and MUST be ASCII.
      If referer is a URL with non-ASCII chars, percent-encode it.
    """
    headers: dict[str, str] = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    # Optional analytics headers
    referer_env = os.getenv("OR_HTTP_REFERER", "")
    title_env = os.getenv("OR_X_TITLE", "")

    # Percent-encode referer URL first (RFC3986), then enforce ASCII
    if referer_env:
        # Preserve scheme and host; percent-encode path/query/fragments
        try:
            parsed = urllib.parse.urlsplit(referer_env)
            safe_path = urllib.parse.quote(parsed.path or "", safe="/")
            safe_query = urllib.parse.quote_plus(parsed.query or "", safe="=&")
            safe_frag = urllib.parse.quote(parsed.fragment or "", safe="")
            rebuilt = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, safe_path, safe_query, safe_frag))
            referer_ascii = _ascii_or_none(rebuilt)
        except Exception:
            referer_ascii = _ascii_or_none(referer_env)
        if referer_ascii:
            headers["HTTP-Referer"] = referer_ascii

    # Title must be pure ASCII; if it contains Persian/emoji, drop it or transliterate externally
    title_ascii = _ascii_or_none(title_env)
    if title_ascii:
        headers["X-Title"] = title_ascii

    return headers

async def _call_openrouter(prompt: str) -> str:
    headers = _safe_openrouter_headers()

    body = {
        "model": settings.llm_model or "openrouter/auto",
        "messages": [
            {"role": "system", "content": "You are a helpful Farsi assistant."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 220
    }

    # Optional: catch header errors early with httpx.Headers validation
    try:
        _ = httpx.Headers(headers)
    except Exception as e:
        raise ValueError(f"Invalid HTTP header value detected (ASCII only). Sanitize OR_HTTP_REFERER/OR_X_TITLE. Details: {e}") from e

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{settings.llm_api_base}/chat/completions", headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
