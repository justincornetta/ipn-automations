from __future__ import annotations

from typing import Any


def render_slack_message(
    *,
    topic: str,
    meeting_date: str,
    group: str,
    summary_markdown: str,
    drive_folder_url: str,
    attendees: list[str] | None = None,
) -> str:
    attendee_text = ""
    if attendees:
        visible = ", ".join(attendees[:12])
        suffix = f" +{len(attendees) - 12} more" if len(attendees) > 12 else ""
        attendee_text = f"\n*Attendees:* {visible}{suffix}"

    return (
        f"*{topic}*\n"
        f"*Date:* {meeting_date} | *Group:* `{group}`{attendee_text}\n"
        f"*Archive:* {drive_folder_url}\n\n"
        f"{summary_markdown.strip()}"
    ).strip()


def metadata_for_slack(recording: dict[str, Any], group: str) -> dict[str, Any]:
    return {
        "event_type": "ipn_meeting_summary",
        "event_payload": {
            "group": group,
            "meeting_id": recording.get("meeting_id"),
            "meeting_uuid": recording.get("meeting_uuid"),
            "recording_file_id": recording.get("recording_file_id"),
        },
    }
