from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import email.utils
import re
from typing import Any

from googleapiclient.discovery import build

from .google_auth import GoogleAuth
from .text_utils import clean_whitespace


KEYWORD_QUERY = '(psychedelx OR sponsorship OR sponsor OR "prize sponsor" OR prospectus OR partnership)'

# Include messages that involve key IPN alias addresses, even if the subject/snippet
# doesn't include sponsorship keywords (common for warm intros/outreach).
ALIAS_QUERY = (
    "("
    "to:info@intercollegiatepsychedelics.net OR from:info@intercollegiatepsychedelics.net OR "
    "cc:info@intercollegiatepsychedelics.net OR "
    "to:justin@intercollegiatepsychedelics.net OR from:justin@intercollegiatepsychedelics.net OR "
    "cc:justin@intercollegiatepsychedelics.net OR "
    "to:victor@intercollegiatepsychedelics.net OR from:victor@intercollegiatepsychedelics.net OR "
    "cc:victor@intercollegiatepsychedelics.net"
    ")"
)

SPONSOR_QUERY = (
    f"newer_than:1d ({KEYWORD_QUERY} OR {ALIAS_QUERY}) "
    "-in:spam -in:trash -category:promotions -category:social -category:forums"
)

IPN_INTERNAL_DOMAINS = {
    "intercollegiatepsychedelics.net",
}


@dataclass(frozen=True)
class GmailMessage:
    message_id: str
    thread_id: str
    is_outbound: bool
    date_utc: datetime
    from_email: str
    to_emails: tuple[str, ...]
    cc_emails: tuple[str, ...]
    subject: str
    snippet: str


def _parse_email_addresses(value: str) -> list[str]:
    if not value:
        return []
    parsed = email.utils.getaddresses([value])
    emails: list[str] = []
    for _, addr in parsed:
        addr = addr.strip().lower()
        if addr:
            emails.append(addr)
    return emails


def _header(headers: list[dict[str, Any]], name: str) -> str:
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return str(header.get("value", ""))
    return ""


def _parse_rfc2822_datetime(value: str) -> datetime:
    dt = email.utils.parsedate_to_datetime(value)
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _safe_snippet(value: str) -> str:
    value = clean_whitespace(value)
    return value[:240]


def build_gmail_service(auth: GoogleAuth):
    return build("gmail", "v1", credentials=auth.creds, cache_discovery=False)


def search_messages(service, *, user_id: str, query: str = SPONSOR_QUERY, max_results: int = 50) -> list[str]:
    results = service.users().messages().list(userId=user_id, q=query, maxResults=max_results).execute()
    messages = results.get("messages", []) or []
    return [m["id"] for m in messages if "id" in m]


def fetch_message(service, *, user_id: str, message_id: str) -> GmailMessage:
    msg = (
        service.users()
        .messages()
        .get(
            userId=user_id,
            id=message_id,
            format="metadata",
            metadataHeaders=["From", "To", "Cc", "Date", "Subject"],
        )
        .execute()
    )
    payload = msg.get("payload", {}) or {}
    headers = payload.get("headers", []) or []
    label_ids = set(msg.get("labelIds", []) or [])

    from_email = _parse_email_addresses(_header(headers, "From"))[0] if _header(headers, "From") else ""
    to_emails = tuple(_parse_email_addresses(_header(headers, "To")))
    cc_emails = tuple(_parse_email_addresses(_header(headers, "Cc")))
    subject = _header(headers, "Subject").strip()
    date_utc = _parse_rfc2822_datetime(_header(headers, "Date"))
    snippet = _safe_snippet(msg.get("snippet", ""))
    is_outbound = "SENT" in label_ids

    return GmailMessage(
        message_id=msg["id"],
        thread_id=msg.get("threadId", msg["id"]),
        is_outbound=is_outbound,
        date_utc=date_utc,
        from_email=(from_email or "").lower(),
        to_emails=tuple(e.lower() for e in to_emails),
        cc_emails=tuple(e.lower() for e in cc_emails),
        subject=subject,
        snippet=snippet,
    )


def primary_contact_email(message: GmailMessage) -> str | None:
    if message.is_outbound:
        candidates = list(message.to_emails) + list(message.cc_emails)
        for addr in candidates:
            domain = addr.split("@")[-1].lower()
            if domain not in IPN_INTERNAL_DOMAINS:
                return addr
        return None
    return message.from_email or None
