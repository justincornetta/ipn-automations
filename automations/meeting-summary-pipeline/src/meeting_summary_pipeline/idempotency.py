from __future__ import annotations


def should_process_existing_status(status: str | None) -> bool:
    return status != "posted"
