from __future__ import annotations

import html
import re


TIMESTAMP_RE = re.compile(
    r"^\d{2}:\d{2}:\d{2}\.\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}\.\d{3}"
)
TAG_RE = re.compile(r"<[^>]+>")


def vtt_to_text(vtt: str) -> str:
    lines: list[str] = []
    previous = ""

    for raw_line in vtt.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == "WEBVTT" or line.startswith("NOTE"):
            continue
        if TIMESTAMP_RE.match(line):
            continue
        if line.isdigit():
            continue

        line = TAG_RE.sub("", line)
        line = html.unescape(line)
        line = re.sub(r"\s+", " ", line).strip()
        if not line or line == previous:
            continue
        lines.append(line)
        previous = line

    return "\n".join(lines).strip()


def truncate_transcript(text: str, *, max_chars: int = 140_000) -> str:
    if len(text) <= max_chars:
        return text
    head = text[: int(max_chars * 0.7)].rstrip()
    tail = text[-int(max_chars * 0.3) :].lstrip()
    return f"{head}\n\n[Transcript truncated for model context]\n\n{tail}"
