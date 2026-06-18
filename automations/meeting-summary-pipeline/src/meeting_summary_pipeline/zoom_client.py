from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote
import time

import requests

from .models import RecordingFile


ZOOM_AUTH_URL = "https://zoom.us/oauth/token"
ZOOM_API_BASE = "https://api.zoom.us/v2"
TRANSCRIPT_TYPES = {"audio_transcript", "transcript"}
TRANSCRIPT_FILE_TYPES = {"VTT", "TRANSCRIPT"}


class ZoomClient:
    def __init__(self, *, account_id: str, client_id: str, client_secret: str):
        self.account_id = account_id
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token: str | None = None
        self._expires_at = 0.0

    def _token(self) -> str:
        if self._access_token and time.time() < self._expires_at:
            return self._access_token

        resp = requests.post(
            ZOOM_AUTH_URL,
            auth=(self.client_id, self.client_secret),
            data={"grant_type": "account_credentials", "account_id": self.account_id},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        self._expires_at = time.time() + int(data.get("expires_in", 3600)) - 300
        return self._access_token

    def _get(self, endpoint: str, params: dict | None = None) -> dict | None:
        token = self._token()
        resp = requests.get(
            f"{ZOOM_API_BASE}{endpoint}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=30,
        )
        if resp.status_code == 404:
            return None
        if resp.status_code == 429:
            time.sleep(int(resp.headers.get("Retry-After", "5")))
            return self._get(endpoint, params)
        try:
            resp.raise_for_status()
        except requests.HTTPError as exc:
            detail = resp.text[:500]
            raise requests.HTTPError(f"{exc} response={detail}", response=resp) from exc
        return resp.json()

    def _get_all_pages(self, endpoint: str, key: str, params: dict | None = None) -> list[dict]:
        params = dict(params or {})
        params.setdefault("page_size", 300)
        items: list[dict] = []
        while True:
            data = self._get(endpoint, params)
            if not data:
                return items
            items.extend(data.get(key, []) or [])
            next_token = data.get("next_page_token")
            if not next_token:
                return items
            params["next_page_token"] = next_token

    def list_users(self) -> list[dict]:
        return self._get_all_pages("/users", "users", {"status": "active"})

    def list_recent_recordings(self, *, days: int) -> list[dict]:
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=days)
        recordings: list[dict] = []
        for user in self.list_users():
            user_id = user.get("id")
            if not user_id:
                continue
            try:
                data = self._get_all_pages(
                    f"/users/{quote(user_id, safe='')}/recordings",
                    "meetings",
                    {"from": start.isoformat(), "to": end.isoformat()},
                )
            except requests.HTTPError as exc:
                print(f"  Skipping Zoom recordings for user {user_id}: {exc}")
                continue
            recordings.extend(data)
        return recordings

    def get_recording(self, meeting_id: str) -> dict | None:
        encoded = quote(meeting_id, safe="")
        if "/" in meeting_id:
            encoded = quote(encoded, safe="")
        return self._get(f"/meetings/{encoded}/recordings")

    def list_participants(self, meeting_uuid: str) -> list[str]:
        encoded = quote(meeting_uuid, safe="")
        if "/" in meeting_uuid:
            encoded = quote(encoded, safe="")
        try:
            participants = self._get_all_pages(f"/report/meetings/{encoded}/participants", "participants")
        except requests.HTTPError:
            return []
        names: list[str] = []
        seen: set[str] = set()
        for participant in participants:
            name = str(participant.get("name") or participant.get("user_name") or "").strip()
            if name and name.lower() not in seen:
                names.append(name)
                seen.add(name.lower())
        return names

    def download_text(self, download_url: str) -> str:
        resp = requests.get(
            download_url,
            headers={"Authorization": f"Bearer {self._token()}"},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.text


def extract_meeting_id_from_event(event_payload: dict[str, Any] | None) -> str | None:
    if not event_payload:
        return None
    obj = (event_payload.get("payload") or {}).get("object") or {}
    return str(obj.get("uuid") or obj.get("id") or obj.get("meeting_id") or "").strip() or None


def extract_recording_file_id_from_event(event_payload: dict[str, Any] | None) -> str | None:
    if not event_payload:
        return None
    obj = (event_payload.get("payload") or {}).get("object") or {}
    file_obj = (event_payload.get("payload") or {}).get("recording_file") or {}
    if file_obj.get("id"):
        return str(file_obj["id"])
    files = obj.get("recording_files") or []
    for item in files:
        if _is_transcript_file(item):
            return str(item.get("id") or "")
    return None


def _is_transcript_file(file_obj: dict[str, Any]) -> bool:
    recording_type = str(file_obj.get("recording_type") or "").lower()
    file_type = str(file_obj.get("file_type") or "").upper()
    return recording_type in TRANSCRIPT_TYPES or file_type in TRANSCRIPT_FILE_TYPES


def recording_files_from_meeting(meeting: dict[str, Any], *, only_file_id: str | None = None) -> list[RecordingFile]:
    files: list[RecordingFile] = []
    meeting_id = str(meeting.get("id") or meeting.get("meeting_id") or "")
    meeting_uuid = str(meeting.get("uuid") or meeting.get("meeting_uuid") or meeting_id)
    topic = str(meeting.get("topic") or "Zoom Meeting")
    start_time = str(meeting.get("start_time") or meeting.get("recording_start") or "")

    for file_obj in meeting.get("recording_files", []) or []:
        file_id = str(file_obj.get("id") or "")
        if only_file_id and file_id != only_file_id:
            continue
        if not file_id or not _is_transcript_file(file_obj):
            continue
        download_url = str(file_obj.get("download_url") or "").strip()
        if not download_url:
            continue
        files.append(
            RecordingFile(
                id=file_id,
                meeting_id=meeting_id,
                meeting_uuid=meeting_uuid,
                topic=topic,
                start_time=start_time,
                recording_start=file_obj.get("recording_start"),
                recording_end=file_obj.get("recording_end"),
                download_url=download_url,
                file_type=str(file_obj.get("file_type") or ""),
                recording_type=str(file_obj.get("recording_type") or ""),
                status=str(file_obj.get("status") or ""),
                raw=file_obj,
            )
        )
    return files
