import httpx
from typing import Optional
from app.core.config import settings

async def ask_llm(prompt: str) -> str:
    provider = settings.llm_provider.lower().strip()
    if provider == "openrouter":
        return await _call_openrouter(prompt)
    elif provider == "huggingface":
        return await _call_huggingface(prompt)
    else:
        # Safe local fallback (no external call)
        # Extract a brief answer-ish summary: if no data, say unknown.
        if "داده‌های مرتبط:\n—" in prompt:
            return "اطلاعات کافی در دیتابیس موجود نیست."
        # Otherwise, generic concise acknowledgment (RAG-only result)
        return "براساس داده‌های موجود، این گزینه‌ها مناسب‌اند. اگر مورد خاصی مدنظر دارید دقیق‌تر بفرمایید."

async def _call_openrouter(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.llm_model or "openrouter/auto",
        "messages": [
            {"role": "system", "content": "You are a helpful Farsi assistant."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 200
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{settings.llm_api_base}/chat/completions", headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

async def _call_huggingface(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    payload = {"inputs": prompt, "parameters": {"max_new_tokens": 200, "temperature": 0.3}}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(settings.llm_api_base, headers=headers, json=payload)
        resp.raise_for_status()
        out = resp.json()
        # HF responses vary (list/dict). Handle common shapes:
        if isinstance(out, list) and out and "generated_text" in out[0]:
            return out[0]["generated_text"].strip()
        if isinstance(out, dict) and "generated_text" in out:
            return out["generated_text"].strip()
        # Fallback best-effort
        return str(out)[:600]
