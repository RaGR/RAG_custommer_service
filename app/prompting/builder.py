from typing import List, Dict

SYSTEM_POLICY_FA = (
    "تو یک دستیار پاسخ‌گوی فارسی هستی که فقط بر اساس داده‌های زیر پاسخ می‌دهد. "
    "اگر پاسخ در داده‌ها نبود، بگو «اطلاعات کافی در دیتابیس موجود نیست». "
    "پاسخ را کوتاه، دقیق و مودبانه بنویس."
)

def build_context_snippets(items: List[Dict]) -> str:
    lines = []
    for it in items:
        lines.append(f"- نام: {it['name']}\n  توضیح: {it['description']}\n  قیمت: {int(it['price'])} تومان")
    return "\n".join(lines)

def build_prompt(user_text: str, retrieved: List[Dict]) -> str:
    ctx = build_context_snippets(retrieved) if retrieved else "—"
    return (
        f"{SYSTEM_POLICY_FA}\n\n"
        f"### داده‌های مرتبط:\n{ctx}\n\n"
        f"### پرسش کاربر:\n{user_text}\n\n"
        f"### پاسخ فارسی کوتاه:\n"
    )
