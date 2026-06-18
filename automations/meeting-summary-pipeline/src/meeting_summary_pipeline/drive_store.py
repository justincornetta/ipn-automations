from __future__ import annotations

from dataclasses import dataclass
import io
import json
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from .google_auth import GoogleAuth


FOLDER_MIME = "application/vnd.google-apps.folder"


@dataclass(frozen=True)
class FolderState:
    id: str
    web_url: str
    status: str | None


class DriveStore:
    def __init__(self, auth: GoogleAuth):
        self.service = build("drive", "v3", credentials=auth.creds, cache_discovery=False)

    def _find_child(self, *, parent_id: str, name: str, mime_type: str | None = None) -> dict | None:
        escaped = name.replace("'", "\\'")
        parts = [
            f"'{parent_id}' in parents",
            "trashed = false",
            f"name = '{escaped}'",
        ]
        if mime_type:
            parts.append(f"mimeType = '{mime_type}'")
        result = (
            self.service.files()
            .list(
                q=" and ".join(parts),
                fields="files(id,name,mimeType,webViewLink,appProperties)",
                spaces="drive",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        files = result.get("files", []) or []
        return files[0] if files else None

    def _create_folder(
        self,
        *,
        parent_id: str,
        name: str,
        app_properties: dict[str, str] | None = None,
    ) -> dict:
        body = {
            "name": name,
            "mimeType": FOLDER_MIME,
            "parents": [parent_id],
        }
        if app_properties:
            body["appProperties"] = app_properties
        return (
            self.service.files()
            .create(body=body, fields="id,name,webViewLink,appProperties", supportsAllDrives=True)
            .execute()
        )

    def find_folder_by_path(self, path: str) -> str:
        parts = [part.strip() for part in path.split("/") if part.strip()]
        if not parts:
            raise RuntimeError("Drive root path is empty")

        first = parts[0].replace("'", "\\'")
        result = (
            self.service.files()
            .list(
                q=f"name = '{first}' and mimeType = '{FOLDER_MIME}' and trashed = false",
                fields="files(id,name)",
                spaces="drive",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        files = result.get("files", []) or []
        if not files:
            raise RuntimeError(f"Could not find Drive folder '{parts[0]}'. Set MEETING_SUMMARIES_ROOT_FOLDER_ID.")
        parent_id = files[0]["id"]

        for part in parts[1:]:
            found = self._find_child(parent_id=parent_id, name=part, mime_type=FOLDER_MIME)
            if found:
                parent_id = found["id"]
            else:
                parent_id = self._create_folder(parent_id=parent_id, name=part)["id"]
        return parent_id

    def ensure_path(self, *, root_id: str, parts: list[str]) -> FolderState:
        parent_id = root_id
        current: dict[str, Any] | None = None
        for part in parts:
            current = self._find_child(parent_id=parent_id, name=part, mime_type=FOLDER_MIME)
            if current is None:
                current = self._create_folder(parent_id=parent_id, name=part)
            parent_id = current["id"]
        if current is None:
            current = self.service.files().get(fileId=root_id, fields="id,webViewLink,appProperties").execute()
        props = current.get("appProperties", {}) or {}
        return FolderState(id=current["id"], web_url=current.get("webViewLink", ""), status=props.get("ipn_status"))

    def find_folder_by_idempotency_key(self, key: str) -> FolderState | None:
        escaped = key.replace("'", "\\'")
        result = (
            self.service.files()
            .list(
                q=(
                    f"mimeType = '{FOLDER_MIME}' and trashed = false and "
                    f"appProperties has {{ key='ipn_idempotency_key' and value='{escaped}' }}"
                ),
                fields="files(id,name,webViewLink,appProperties)",
                spaces="drive",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        files = result.get("files", []) or []
        if not files:
            return None
        props = files[0].get("appProperties", {}) or {}
        return FolderState(id=files[0]["id"], web_url=files[0].get("webViewLink", ""), status=props.get("ipn_status"))

    def set_app_properties(self, file_id: str, props: dict[str, str]) -> None:
        self.service.files().update(
            fileId=file_id,
            body={"appProperties": props},
            fields="id,appProperties",
            supportsAllDrives=True,
        ).execute()

    def upload_text(self, *, parent_id: str, name: str, text: str, mime_type: str = "text/plain") -> str:
        existing = self._find_child(parent_id=parent_id, name=name)
        media = MediaIoBaseUpload(io.BytesIO(text.encode("utf-8")), mimetype=mime_type, resumable=False)
        if existing:
            result = (
                self.service.files()
                .update(fileId=existing["id"], media_body=media, fields="id", supportsAllDrives=True)
                .execute()
            )
        else:
            result = (
                self.service.files()
                .create(
                    body={"name": name, "parents": [parent_id]},
                    media_body=media,
                    fields="id",
                    supportsAllDrives=True,
                )
                .execute()
            )
        return result["id"]

    def write_json(self, *, parent_id: str, name: str, data: dict[str, Any]) -> str:
        return self.upload_text(
            parent_id=parent_id,
            name=name,
            text=json.dumps(data, indent=2, sort_keys=True),
            mime_type="application/json",
        )
