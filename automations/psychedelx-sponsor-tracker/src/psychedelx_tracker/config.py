from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Config:
    slack_bot_token: str
    slack_channel_id: str
    google_client_id: str
    google_client_secret: str
    google_refresh_token: str
    google_user_email: str
    tracker_sheet_id: str
    tracker_tab_name: str
    audit_tab_name: str


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required env var: {name}")
    return value.strip()


def load_config() -> Config:
    return Config(
        slack_bot_token=_env("SLACK_BOT_TOKEN"),
        slack_channel_id=os.getenv("SLACK_CHANNEL_ID", "C0B4G57B719").strip() or "C0B4G57B719",
        google_client_id=_env("GOOGLE_CLIENT_ID"),
        google_client_secret=_env("GOOGLE_CLIENT_SECRET"),
        google_refresh_token=_env("GOOGLE_REFRESH_TOKEN"),
        google_user_email=_env("GOOGLE_USER_EMAIL"),
        tracker_sheet_id=os.getenv(
            "TRACKER_SHEET_ID",
            "1E_kHmYj-JZ8MCDDeeJWqOPUbIqnu5AgRdC2uBfmp3fw",
        ).strip()
        or "1E_kHmYj-JZ8MCDDeeJWqOPUbIqnu5AgRdC2uBfmp3fw",
        tracker_tab_name=os.getenv("TRACKER_TAB_NAME", "PsychedelX 2026 Pipeline").strip()
        or "PsychedelX 2026 Pipeline",
        audit_tab_name=os.getenv("AUDIT_TAB_NAME", "Automation Audit").strip() or "Automation Audit",
    )

