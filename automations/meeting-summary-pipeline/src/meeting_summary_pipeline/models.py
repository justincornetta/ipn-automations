from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class RecordingFile:
    id: str
    meeting_id: str
    meeting_uuid: str
    topic: str
    start_time: str
    recording_start: str | None
    recording_end: str | None
    download_url: str
    file_type: str
    recording_type: str
    status: str
    raw: dict[str, Any]

    @property
    def idempotency_key(self) -> str:
        return f"{self.meeting_uuid or self.meeting_id}:{self.id}"


@dataclass(frozen=True)
class MeetingArtifact:
    recording_file: RecordingFile
    group: str
    folder_name: str
    year: str
    transcript_vtt: str
    transcript_text: str
    summary_markdown: str
    slack_message: str
    metadata: dict[str, Any]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
