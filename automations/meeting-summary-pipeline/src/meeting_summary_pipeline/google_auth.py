from __future__ import annotations

from dataclasses import dataclass

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/drive",
]


@dataclass(frozen=True)
class GoogleAuth:
    creds: Credentials


def build_credentials(*, client_id: str, client_secret: str, refresh_token: str) -> GoogleAuth:
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return GoogleAuth(creds=creds)
