from __future__ import annotations

import re


def clean_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def safe_summary(subject: str, snippet: str, max_len: int = 180) -> str:
    base = clean_whitespace(subject) or ""
    if not base:
        base = clean_whitespace(snippet)
    base = base or "Sponsorship-related email."
    return (base[: max_len - 1] + "…") if len(base) > max_len else base

