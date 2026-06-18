from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Config:
    zoom_account_id: str
    zoom_client_id: str
    zoom_client_secret: str
    openai_api_key: str | None
    openai_model: str
    slack_bot_token: str
    slack_channel_id: str | None
    slack_channel_name: str
    slack_create_channel: bool
    google_client_id: str
    google_client_secret: str
    google_refresh_token: str
    google_service_account_json: str | None
    drive_root_folder_id: str | None
    drive_root_path: str
    poll_window_days: int
    retry_missing_transcript_hours: int
    include_keywords: tuple[str, ...]
    exclude_keywords: tuple[str, ...]


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required env var: {name}")
    return value.strip()


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return value.strip()


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _csv_env(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value.strip())


def load_config() -> Config:
    return Config(
        zoom_account_id=_env("ZOOM_ACCOUNT_ID"),
        zoom_client_id=_env("ZOOM_CLIENT_ID"),
        zoom_client_secret=_env("ZOOM_CLIENT_SECRET"),
        openai_api_key=_optional_env("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4-nano").strip() or "gpt-5.4-nano",
        slack_bot_token=_env("SLACK_BOT_TOKEN"),
        slack_channel_id=_optional_env("SLACK_MEETING_SUMMARIES_CHANNEL_ID"),
        slack_channel_name=os.getenv("SLACK_MEETING_SUMMARIES_CHANNEL_NAME", "meeting-summaries").strip()
        or "meeting-summaries",
        slack_create_channel=_bool_env("SLACK_CREATE_MEETING_SUMMARIES_CHANNEL", False),
        google_client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
        google_refresh_token=os.getenv("GOOGLE_REFRESH_TOKEN", "").strip(),
        google_service_account_json=_optional_env("GOOGLE_SERVICE_ACCOUNT_JSON"),
        drive_root_folder_id=_optional_env("MEETING_SUMMARIES_ROOT_FOLDER_ID"),
        drive_root_path=os.getenv(
            "MEETING_SUMMARIES_ROOT_PATH",
            "Main - IPN/Technology/Automations/Meeting Summaries",
        ).strip()
        or "Main - IPN/Technology/Automations/Meeting Summaries",
        poll_window_days=_int_env("MEETING_SUMMARY_POLL_WINDOW_DAYS", 2),
        retry_missing_transcript_hours=_int_env("MEETING_SUMMARY_RETRY_HOURS", 24),
        include_keywords=_csv_env("MEETING_INCLUDE_KEYWORDS"),
        exclude_keywords=_csv_env("MEETING_EXCLUDE_KEYWORDS"),
    )
