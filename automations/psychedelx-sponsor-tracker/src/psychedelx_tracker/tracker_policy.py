from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
import re

from .text_utils import clean_whitespace


class Direction(str, Enum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


@dataclass(frozen=True)
class Classification:
    stage: str | None
    follow_up_days: int | None
    clear_follow_up: bool
    reason: str


NEGATIVE_PATTERNS = (
    r"\bno budget\b",
    r"\bnot (?:this|the) year\b",
    r"\bcan't sponsor\b",
    r"\bcannot sponsor\b",
    r"\bunable to sponsor\b",
    r"\bdeclin(?:e|ing)\b",
    r"\bpass on\b",
)

WON_PATTERNS = (
    r"\bconfirmed sponsor\b",
    r"\bwe (?:will|can) sponsor\b",
    r"\bwe're in\b",
    r"\bpayment (?:sent|submitted|complete|confirmed)\b",
    r"\binvoice paid\b",
)

CONTRACT_SENT_PATTERNS = (
    r"\bagreement (?:is )?(?:attached|sent|shared)\b",
    r"\bsponsorship agreement\b",
    r"\bcontract (?:is )?(?:attached|sent|shared)\b",
)

NEGOTIATING_PATTERNS = (
    r"\bterms\b",
    r"\bpackage\b",
    r"\bdeliverables\b",
    r"\binvoice\b",
    r"\bpayment\b",
    r"\blegal review\b",
)

ENGAGED_PATTERNS = (
    r"\binterested\b",
    r"\bprospectus\b",
    r"\bcan you send\b",
    r"\bhappy to chat\b",
    r"\bschedule\b",
    r"\bmeeting\b",
    r"\bcall\b",
    r"\bquestions?\b",
    r"\btell me more\b",
)

OUTREACH_PATTERNS = (
    r"\bsponsor(?:ship)?\b",
    r"\bpsychedelx\b",
    r"\bprospectus\b",
    r"\bpartnership\b",
)

NEW_ROW_SPONSOR_PATTERNS = (
    r"\bsponsor(?:ship)?\b",
    r"\bprize sponsor\b",
    r"\bprospectus\b",
    r"\bpartnership\b",
)

NON_SPONSOR_PROGRAM_PATTERNS = (
    r"\bpanelist\b",
    r"\bkeynote\b",
    r"\bjudge\b",
    r"\btalk coach\b",
    r"\bparticipant\b",
    r"\bworkshop\b",
    r"\bmedia release\b",
)

INTERNAL_EMAIL_PATTERN = re.compile(r"@intercollegiatepsychedelics\.net\b", re.IGNORECASE)


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def classify_message(text: str, direction: Direction, current_stage: str = "") -> Classification:
    normalized = clean_whitespace(text)
    stage = current_stage.strip()

    if _matches_any(normalized, NEGATIVE_PATTERNS):
        return Classification("Closed Lost", None, True, "clear decline or no-budget reply")

    if _matches_any(normalized, WON_PATTERNS):
        return Classification("Closed Won", None, True, "clear sponsorship confirmation")

    if _matches_any(normalized, CONTRACT_SENT_PATTERNS):
        return Classification("Contract Sent", 2, False, "contract or agreement sent/shared")

    if _matches_any(normalized, NEGOTIATING_PATTERNS):
        return Classification("Negotiating", 2, False, "terms, deliverables, invoice, or payment discussion")

    if direction == Direction.INBOUND and _matches_any(normalized, ENGAGED_PATTERNS):
        return Classification("Engaged", 2, False, "sponsor replied with interest or next-step discussion")

    if direction == Direction.OUTBOUND and stage in ("", "Lead Generation") and _matches_any(normalized, OUTREACH_PATTERNS):
        return Classification("Contacted", 2, False, "outbound sponsorship outreach")

    return Classification(None, None, False, "log only; no clear stage change")


def should_create_new_tracker_row(text: str, *, direction: Direction, recipient_email: str) -> bool:
    normalized = clean_whitespace(text)
    if direction != Direction.OUTBOUND:
        return False
    if INTERNAL_EMAIL_PATTERN.search(recipient_email or ""):
        return False
    if _matches_any(normalized, NON_SPONSOR_PROGRAM_PATTERNS):
        return False
    return _matches_any(normalized, NEW_ROW_SPONSOR_PATTERNS)


def add_business_days(start: date, business_days: int) -> date:
    current = start
    added = 0
    while added < business_days:
        current = current + timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


def build_log_line(
    *,
    message_date: date,
    direction: Direction,
    contact_or_org: str,
    summary: str,
    next_step: str,
) -> str:
    clean_summary = clean_whitespace(summary)
    clean_next_step = clean_whitespace(next_step) or "None."
    return (
        f"{message_date.isoformat()} - Auto-log: {direction.value} with "
        f"{contact_or_org}. {clean_summary} Next step: {clean_next_step}"
    )

