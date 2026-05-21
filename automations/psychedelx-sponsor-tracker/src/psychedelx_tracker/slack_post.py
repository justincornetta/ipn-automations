from __future__ import annotations

import requests


def post_message(*, token: str, channel: str, text: str) -> str:
    resp = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}"},
        json={"channel": channel, "text": text, "unfurl_links": False},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack error: {data.get('error')}")
    return str(data.get("ts"))

