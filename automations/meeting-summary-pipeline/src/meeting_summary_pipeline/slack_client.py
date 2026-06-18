from __future__ import annotations

import requests


class SlackClient:
    def __init__(self, token: str):
        self.token = token

    def _post(self, method: str, payload: dict) -> dict:
        resp = requests.post(
            f"https://slack.com/api/{method}",
            headers={"Authorization": f"Bearer {self.token}"},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack {method} error: {data.get('error')}")
        return data

    def _get(self, method: str, params: dict) -> dict:
        resp = requests.get(
            f"https://slack.com/api/{method}",
            headers={"Authorization": f"Bearer {self.token}"},
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack {method} error: {data.get('error')}")
        return data

    def get_or_create_private_channel(self, *, channel_id: str | None, name: str, create: bool) -> str:
        if channel_id:
            return channel_id
        if not create:
            raise RuntimeError(
                "SLACK_MEETING_SUMMARIES_CHANNEL_ID is missing. Create private channel "
                f"#{name}, invite the IPN bot, and set this secret; or set "
                "SLACK_CREATE_MEETING_SUMMARIES_CHANNEL=true with groups:write/groups:read scopes."
            )

        try:
            data = self._post("conversations.create", {"name": name, "is_private": True})
            return data["channel"]["id"]
        except RuntimeError as exc:
            if "name_taken" not in str(exc):
                raise

        cursor = None
        while True:
            params = {"types": "private_channel", "limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = self._get("conversations.list", params)
            for channel in data.get("channels", []):
                if channel.get("name") == name:
                    return channel["id"]
            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        raise RuntimeError(f"Slack channel #{name} exists, but the bot could not find it. Invite the bot and set its ID.")

    def post_message(self, *, channel: str, text: str, metadata: dict | None = None, dry_run: bool = False) -> str:
        if dry_run:
            return "dry-run"
        payload = {
            "channel": channel,
            "text": text,
            "unfurl_links": False,
            "unfurl_media": False,
        }
        if metadata:
            payload["metadata"] = metadata
        data = self._post("chat.postMessage", payload)
        return str(data["ts"])
