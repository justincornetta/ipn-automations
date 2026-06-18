from __future__ import annotations

from dataclasses import dataclass
import json

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account


SCOPES = [
    "https://www.googleapis.com/auth/drive",
]


@dataclass(frozen=True)
class GoogleAuth:
    creds: Credentials


def build_credentials(
    *,
    client_id: str = "",
    client_secret: str = "",
    refresh_token: str = "",
    service_account_json: str | None = None,
) -> GoogleAuth:
    if service_account_json:
        info = json.loads(service_account_json)
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        return GoogleAuth(creds=creds)

    if not client_id or not client_secret or not refresh_token:
        raise RuntimeError("Missing Google credentials. Set GOOGLE_SERVICE_ACCOUNT_JSON or OAuth client/refresh token secrets.")

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
