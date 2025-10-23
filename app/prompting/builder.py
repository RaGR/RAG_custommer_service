import re
from typing import List, Dict
from app.core.config import settings

SYSTEM_POLICY_FA = (
    "تو یک دستیار فارسی هستی که فقط بر اساس داده‌های ارائه‌شده پاسخ می‌دهی. "
    "اگر پاسخ در داده‌ها نبود، دقیقا بنویس: «اطلاعات کافی در دیتابیس موجود نیست». "
    "پاسخ را کوتاه و مشخص (۱–۳ جمله) بنویس و از حدس زدن خودداری کن."
)

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)

def _sanitize_text(txt: str, max_chars: int) -> str:
    if not txt:
        return ""
    t = txt.replace("\u200c", " ")  # ZWNJ → space
    t = _URL_RE.sub("", t)          # strip urls
    t = re.sub(r"[<>`$]", "", t)    # strip risky chars
    t = re.sub(r"\s+", " ", t).strip()
    return t[:max_chars]

def build_context_snippets(items: List[Dict]) -> str:
    # ALLOW-LIST: name, description, price
    lines = []
    max_len = settings.max_desc_chars
    for it in items:
        name = _sanitize_text(str(it.get("name","")), 120)
        desc = _sanitize_text(str(it.get("description","")), max_len)
        price = int(it.get("price") or 0)
        lines.append(f"- نام: {name}\n  توضیح: {desc}\n  قیمت: {price} تومان")
    return "\n".join(lines) if lines else "—"

def build_prompt(user_text: str, retrieved: List[Dict]) -> str:
    ctx = build_context_snippets(retrieved)
    user = _sanitize_text(user_text, 300)
    return (
        f"{SYSTEM_POLICY_FA}\n\n"
        f"### داده‌های مرتبط (از دیتابیس داخلی):\n{ctx}\n\n"
        f"### پرسش کاربر:\n{user}\n\n"
        f"### دستورالعمل پاسخ:\n"
        f"- اگر موردی دقیقاً مناسب است همان را نام ببر و یک دلیل کوتاه بگو.\n"
        f"- اگر چند مورد نزدیک‌اند، ۱ تا ۳ گزینهٔ برتر را لیست کن.\n"
        f"- اگر هیچ اطلاعاتی نبود، بنویس: «اطلاعات کافی در دیتابیس موجود نیست».\n\n"
        f"### پاسخ نهایی فارسی:\n"
    )
