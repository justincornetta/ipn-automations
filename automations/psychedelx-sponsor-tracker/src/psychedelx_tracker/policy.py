from __future__ import annotations

from datetime import date, timedelta


def add_business_days(start: date, business_days: int) -> date:
    current = start
    remaining = business_days
    while remaining > 0:
        current = current + timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current

