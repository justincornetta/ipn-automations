from __future__ import annotations

from pathlib import Path
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from google_auth_oauthlib.flow import InstalledAppFlow

from meeting_summary_pipeline.google_auth import SCOPES


def main() -> None:
    client_id = input("Google OAuth client ID: ").strip()
    client_secret = input("Google OAuth client secret: ").strip()
    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        },
        scopes=SCOPES,
    )
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    print("\nGOOGLE_REFRESH_TOKEN:")
    print(creds.refresh_token)


if __name__ == "__main__":
    main()
