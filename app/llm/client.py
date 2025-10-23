import os, re, asyncio
import httpx
from app.core.config import settings

_ASCII_RE = re.compile(r"[^\x20-\x7E]")

def _ascii_or_none(v: str | None, max_len=256):
    if not v: return None
    s = _ASCII_RE.sub("", v.strip())
    return s[:max_len] if s else None

def _headers_openrouter():
    key = _ASCII_RE.sub("", (settings.llm_api_key or "").strip())
    if not key:
        raise RuntimeError("openrouter api key missing")
    h = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    ref = _ascii_or_none(os.getenv("OR_HTTP_REFERER", ""))
    ttl = _ascii_or_none(os.getenv("OR_X_TITLE", ""))
    if ref: h["HTTP-Referer"] = ref
    if ttl: h["X-Title"] = ttl
    return h

async def _post_json(url, headers, body, timeout_s):
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        return resp.json()

async def _try_openrouter(prompt: str):
    if not (settings.llm_api_base and settings.llm_api_key):
        raise RuntimeError("openrouter not configured")
    headers = _headers_openrouter()
    body = {
        "model": settings.llm_model or "openrouter/auto",
        "messages": [
            {"role": "system", "content": "You are a helpful Farsi assistant."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 220
    }
    data = await _post_json(f"{settings.llm_api_base}/chat/completions", headers, body, settings.llm_timeout_s)
    return data["choices"][0]["message"]["content"].strip()

async def _try_hf(prompt: str):
    base = (settings.hf_api_base or "").strip()
    key = _ASCII_RE.sub("", (settings.hf_api_key or "").strip())
    if not (base and key):
        raise RuntimeError("hf not configured")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    body = {"inputs": prompt, "parameters": {"max_new_tokens": 220, "temperature": 0.2}}
    data = await _post_json(base, headers, body, settings.llm_timeout_s)
    if isinstance(data, list) and data and "generated_text" in data[0]:
        return data[0]["generated_text"].strip()
    if isinstance(data, dict) and "generated_text" in data:
        return data["generated_text"].strip()
    # Fallback parsing
    return str(data)[:600]

async def ask_llm(prompt: str) -> str:
    # provider chain with retries
    providers = []
    if settings.llm_provider.lower() == "openrouter":
        providers = ["openrouter", "hf"]
    elif settings.llm_provider.lower() == "huggingface":
        providers = ["hf", "openrouter"]
    else:
        providers = []

    for p in providers:
        for _ in range(settings.llm_retries + 1):
            try:
                if p == "openrouter":
                    return await _try_openrouter(prompt)
                else:
                    return await _try_hf(prompt)
            except Exception as e:
                await asyncio.sleep(0.6)
                last_err = e
        # try next provider
    # Final fallback
    if "داده‌های مرتبط:\n—" in prompt:
        return "اطلاعات کافی در دیتابیس موجود نیست."
    return "براساس داده‌های موجود، این گزینه‌ها مناسب‌اند. اگر مورد خاصی مدنظر دارید دقیق‌تر بفرمایید."
