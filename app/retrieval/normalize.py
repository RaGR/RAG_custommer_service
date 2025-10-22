def normalize_query(txt: str) -> str:
    if not txt:
        return ""
    s = txt.strip()
    # unify Arabic/Farsi characters where it often causes mismatch
    s = s.replace("ي", "ی").replace("ك", "ک")
    # collapse spaces
    while "  " in s:
        s = s.replace("  ", " ")
    return s
