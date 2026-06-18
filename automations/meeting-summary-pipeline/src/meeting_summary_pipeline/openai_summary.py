from __future__ import annotations

import json
from typing import Any

import requests

from .transcript import truncate_transcript


SYSTEM_PROMPT = """You summarize internal Intercollegiate Psychedelics Network meetings for directors.
Use only the transcript and metadata provided. Be concise, concrete, and operationally useful.
If an owner, decision, due date, or blocker is not stated, say "Not specified" instead of guessing.
Return Markdown with exactly these sections:

## Executive Summary
- 3 to 6 bullets.

## Key Decisions
- Bullets, or "None stated."

## Action Items
- Owner: task (due date if stated).

## Cross-Team FYIs
- Bullets for developments other directors should know.

## Risks / Blockers
- Bullets, or "None stated."
"""


def _extract_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"].strip()
    parts: list[str] = []
    for item in data.get("output", []) or []:
        for content in item.get("content", []) or []:
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts).strip()


def generate_summary(
    *,
    api_key: str,
    model: str,
    topic: str,
    meeting_date: str,
    group: str,
    attendees: list[str],
    transcript_text: str,
) -> str:
    user_payload = {
        "topic": topic,
        "meeting_date": meeting_date,
        "group": group,
        "attendees": attendees,
        "transcript": truncate_transcript(transcript_text),
    }
    resp = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "input": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        },
        timeout=120,
    )
    resp.raise_for_status()
    text = _extract_text(resp.json())
    if not text:
        raise RuntimeError("OpenAI returned an empty summary")
    return text
