from __future__ import annotations

from datetime import datetime, timezone
import traceback
from typing import Any

from .classify import classify_meeting, date_prefix, folder_name_for
from .config import Config
from .drive_store import DriveStore
from .google_auth import build_credentials
from .idempotency import should_process_existing_status
from .models import RecordingFile, utc_now_iso
from .openai_summary import generate_summary
from .slack_client import SlackClient
from .slack_render import metadata_for_slack, render_slack_message
from .transcript import vtt_to_text
from .zoom_client import (
    ZoomClient,
    extract_meeting_id_from_event,
    extract_recording_file_id_from_event,
    recording_files_from_meeting,
)


class MeetingSummaryPipeline:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.zoom = ZoomClient(
            account_id=cfg.zoom_account_id,
            client_id=cfg.zoom_client_id,
            client_secret=cfg.zoom_client_secret,
        )
        auth = build_credentials(
            client_id=cfg.google_client_id,
            client_secret=cfg.google_client_secret,
            refresh_token=cfg.google_refresh_token,
            service_account_json=cfg.google_service_account_json,
        )
        self.drive = DriveStore(auth)
        self.slack = SlackClient(cfg.slack_bot_token)
        self._root_folder_id: str | None = None
        self._slack_channel_id: str | None = None

    def _root_id(self) -> str:
        if self._root_folder_id:
            return self._root_folder_id
        self._root_folder_id = self.cfg.drive_root_folder_id or self.drive.find_folder_by_path(self.cfg.drive_root_path)
        return self._root_folder_id

    def _slack_channel(self) -> str:
        if self._slack_channel_id:
            return self._slack_channel_id
        self._slack_channel_id = self.slack.get_or_create_private_channel(
            channel_id=self.cfg.slack_channel_id,
            name=self.cfg.slack_channel_name,
            create=self.cfg.slack_create_channel,
        )
        return self._slack_channel_id

    def _allowed_topic(self, topic: str) -> bool:
        text = topic.lower()
        if self.cfg.include_keywords and not any(keyword in text for keyword in self.cfg.include_keywords):
            return False
        if self.cfg.exclude_keywords and any(keyword in text for keyword in self.cfg.exclude_keywords):
            return False
        return True

    def _audit(self, *, name: str, data: dict[str, Any]) -> None:
        root = self._root_id()
        audit = self.drive.ensure_path(root_id=root, parts=["_audit"])
        self.drive.write_json(parent_id=audit.id, name=name, data=data)

    def process_event(
        self,
        *,
        event_payload: dict[str, Any] | None,
        meeting_id: str | None = None,
        recording_file_id: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        resolved_meeting_id = meeting_id or extract_meeting_id_from_event(event_payload)
        resolved_file_id = recording_file_id or extract_recording_file_id_from_event(event_payload)
        if not resolved_meeting_id:
            return {"status": "ignored", "reason": "missing meeting id"}

        meeting = self.zoom.get_recording(resolved_meeting_id)
        if not meeting:
            self._audit(
                name=f"{utc_now_iso()}__missing-recording.json".replace(":", "-"),
                data={"status": "missing_recording", "meeting_id": resolved_meeting_id, "event": event_payload},
            )
            return {"status": "retry", "reason": "recording not available", "meeting_id": resolved_meeting_id}

        return self._process_meeting(meeting, only_file_id=resolved_file_id, dry_run=dry_run)

    def poll_recent(self, *, dry_run: bool = False) -> dict[str, Any]:
        meetings = self.zoom.list_recent_recordings(days=self.cfg.poll_window_days)
        results: list[dict[str, Any]] = []
        for meeting in meetings:
            results.append(self._process_meeting(meeting, only_file_id=None, dry_run=dry_run))
        return {
            "status": "ok",
            "mode": "poll",
            "meetings_checked": len(meetings),
            "results": results,
        }

    def _process_meeting(self, meeting: dict[str, Any], *, only_file_id: str | None, dry_run: bool) -> dict[str, Any]:
        topic = str(meeting.get("topic") or "Zoom Meeting")
        if not self._allowed_topic(topic):
            return {"status": "ignored", "reason": "topic excluded", "topic": topic}

        transcript_files = recording_files_from_meeting(meeting, only_file_id=only_file_id)
        if not transcript_files:
            self._audit(
                name=f"{utc_now_iso()}__missing-transcript.json".replace(":", "-"),
                data={
                    "status": "missing_transcript",
                    "topic": topic,
                    "meeting_id": meeting.get("id"),
                    "meeting_uuid": meeting.get("uuid"),
                    "only_file_id": only_file_id,
                },
            )
            return {"status": "retry", "reason": "transcript not available", "topic": topic}

        results = []
        for recording_file in transcript_files:
            results.append(self._process_recording_file(recording_file, dry_run=dry_run))
        return {"status": "ok", "topic": topic, "files": results}

    def _process_recording_file(self, recording_file: RecordingFile, *, dry_run: bool) -> dict[str, Any]:
        existing = self.drive.find_folder_by_idempotency_key(recording_file.idempotency_key)
        if existing and not should_process_existing_status(existing.status):
            return {"status": "skipped", "reason": "already posted", "recording_file_id": recording_file.id}

        group = classify_meeting(recording_file.topic)
        year, folder_name = folder_name_for(recording_file.topic, recording_file.start_time)
        root = self._root_id()
        folder = existing or self.drive.ensure_path(root_id=root, parts=[year, group, folder_name])
        self.drive.set_app_properties(
            folder.id,
            {
                "ipn_idempotency_key": recording_file.idempotency_key,
                "ipn_status": "processing",
                "ipn_group": group,
            },
        )

        try:
            transcript_vtt = self.zoom.download_text(recording_file.download_url)
            transcript_text = vtt_to_text(transcript_vtt)
            if not transcript_text:
                raise RuntimeError("Transcript file downloaded but produced no text")

            attendees = self.zoom.list_participants(recording_file.meeting_uuid)
            _year, meeting_date = date_prefix(recording_file.start_time)
            summary = generate_summary(
                api_key=self.cfg.openai_api_key,
                model=self.cfg.openai_model,
                topic=recording_file.topic,
                meeting_date=meeting_date,
                group=group,
                attendees=attendees,
                transcript_text=transcript_text,
            )
            slack_message = render_slack_message(
                topic=recording_file.topic,
                meeting_date=meeting_date,
                group=group,
                summary_markdown=summary,
                drive_folder_url=folder.web_url,
                attendees=attendees,
            )

            metadata = self._metadata(recording_file, group, attendees, folder.web_url)
            self.drive.upload_text(parent_id=folder.id, name="transcript.vtt", text=transcript_vtt, mime_type="text/vtt")
            self.drive.upload_text(parent_id=folder.id, name="transcript.txt", text=transcript_text)
            self.drive.upload_text(parent_id=folder.id, name="summary.md", text=summary, mime_type="text/markdown")
            self.drive.upload_text(parent_id=folder.id, name="slack-message.md", text=slack_message, mime_type="text/markdown")
            self.drive.write_json(parent_id=folder.id, name="metadata.json", data=metadata)

            ts = self.slack.post_message(
                channel=self._slack_channel(),
                text=slack_message,
                metadata=metadata_for_slack(
                    {
                        "meeting_id": recording_file.meeting_id,
                        "meeting_uuid": recording_file.meeting_uuid,
                        "recording_file_id": recording_file.id,
                    },
                    group,
                ),
                dry_run=dry_run,
            )
            self.drive.set_app_properties(
                folder.id,
                {
                    "ipn_idempotency_key": recording_file.idempotency_key,
                    "ipn_status": "posted" if not dry_run else "dry_run",
                    "ipn_group": group,
                    "ipn_slack_ts": ts,
                },
            )
            return {
                "status": "posted" if not dry_run else "dry_run",
                "recording_file_id": recording_file.id,
                "group": group,
                "drive_folder": folder.web_url,
                "slack_ts": ts,
            }
        except Exception as exc:  # noqa: BLE001
            error_data = {
                "status": "failed",
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "recording_file_id": recording_file.id,
                "meeting_uuid": recording_file.meeting_uuid,
                "failed_at": utc_now_iso(),
            }
            self.drive.write_json(parent_id=folder.id, name="last-error.json", data=error_data)
            self.drive.set_app_properties(
                folder.id,
                {
                    "ipn_idempotency_key": recording_file.idempotency_key,
                    "ipn_status": "failed",
                    "ipn_group": group,
                },
            )
            return {"status": "failed", "recording_file_id": recording_file.id, "error": str(exc)}

    def _metadata(
        self,
        recording_file: RecordingFile,
        group: str,
        attendees: list[str],
        drive_folder_url: str,
    ) -> dict[str, Any]:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "group": group,
            "topic": recording_file.topic,
            "meeting_id": recording_file.meeting_id,
            "meeting_uuid": recording_file.meeting_uuid,
            "recording_file_id": recording_file.id,
            "recording_type": recording_file.recording_type,
            "file_type": recording_file.file_type,
            "start_time": recording_file.start_time,
            "recording_start": recording_file.recording_start,
            "recording_end": recording_file.recording_end,
            "idempotency_key": recording_file.idempotency_key,
            "attendees": attendees,
            "drive_folder_url": drive_folder_url,
        }
