from __future__ import annotations

import re
from datetime import datetime


GROUP_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("board", ("board", "bod", "director", "directors", "governance")),
    ("community", ("community", "membership", "member experience", "revitalizing ipn community")),
    ("psychedelx", ("psychedelx", "psychedel x", "conference")),
    ("ipn-labs", ("ipn labs", "lab seminar", "labs programming", "seminar", "journal club")),
    ("operations", ("operations", "strategy", "ops", "finance", "partnership", "sponsor")),
)


def classify_meeting(topic: str) -> str:
    text = topic.lower()
    for group, keywords in GROUP_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return group
    return "uncategorized"


def slugify(value: str, *, max_len: int = 72) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return (value[:max_len].strip("-") or "zoom-meeting")


def date_prefix(start_time: str) -> tuple[str, str]:
    try:
        dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    except ValueError:
        dt = datetime.utcnow()
    return dt.strftime("%Y"), dt.strftime("%Y-%m-%d")


def folder_name_for(topic: str, start_time: str) -> tuple[str, str]:
    year, day = date_prefix(start_time)
    return year, f"{day}__{slugify(topic)}"
