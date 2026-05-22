from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
import re


TRACKER_URL_DEFAULT = "https://docs.google.com/spreadsheets/d/1E_kHmYj-JZ8MCDDeeJWqOPUbIqnu5AgRdC2uBfmp3fw/edit"
CLOSED_STAGES = {"Closed Won", "Closed Lost"}


@dataclass(frozen=True)
class OwnerResolution:
    display: str
    unresolved: tuple[str, ...]


@dataclass(frozen=True)
class Reminder:
    organization: str
    owner_display: str
    due_date: date
    stage: str
    suggested_action: str


@dataclass(frozen=True)
class ManualReview:
    organization_or_message: str
    reason: str


@dataclass(frozen=True)
class SentEmail:
    organization_or_contact: str
    owner_display: str
    summary: str


def load_owner_map(path: Path) -> dict[str, str]:
    return json.loads(path.read_text())


def split_owner_names(owner_text: str) -> list[str]:
    cleaned = owner_text.replace("?", "")
    parts = re.split(r"[,/&]|\band\b", cleaned)
    return [part.strip() for part in parts if part.strip()]


def resolve_owner(outreach_assignment: str, ipn_point_of_contact: str, owner_map: dict[str, str]) -> OwnerResolution:
    source = outreach_assignment.strip() or ipn_point_of_contact.strip()
    if not source:
        return OwnerResolution("Unassigned", ())

    displays: list[str] = []
    unresolved: list[str] = []
    for name in split_owner_names(source):
        slack_id = owner_map.get(name)
        if slack_id:
            displays.append(f"<@{slack_id}>")
        else:
            displays.append(name)
            unresolved.append(name)

    return OwnerResolution(", ".join(displays), tuple(unresolved))


def parse_date(value: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def is_open_stage(stage: str) -> bool:
    return stage.strip() not in CLOSED_STAGES


def suggested_follow_up_action(stage: str) -> str:
    stage = stage.strip()
    if stage == "Contacted":
        return "Send first follow-up or try a warmer channel."
    if stage == "Engaged":
        return "Send a concrete next step, call times, or requested details."
    if stage == "Negotiating":
        return "Move terms, deliverables, invoice, or agreement forward."
    if stage == "Contract Sent":
        return "Check on signature or payment status."
    return "Review the latest communication log and send the next appropriate follow-up."


def due_reminders(rows: list[dict[str, str]], today: date, owner_map: dict[str, str]) -> tuple[list[Reminder], list[str]]:
    reminders: list[Reminder] = []
    warnings: list[str] = []

    for row in rows:
        stage = row.get("Pipeline Stage", "").strip()
        if not is_open_stage(stage):
            continue

        raw_due = row.get("Next Follow-Up Due", "")
        due_date = parse_date(raw_due)
        if raw_due and due_date is None:
            warnings.append(f"{row.get('Organization', 'Unknown')}: invalid due date '{raw_due}'")
            continue
        if due_date is None or due_date > today:
            continue

        owner = resolve_owner(row.get("Outreach Assignment", ""), row.get("IPN Point of Contact", ""), owner_map)
        reminders.append(
            Reminder(
                organization=row.get("Organization", "Unknown"),
                owner_display=owner.display,
                due_date=due_date,
                stage=stage or "Unknown",
                suggested_action=suggested_follow_up_action(stage),
            )
        )
        warnings.extend(f"{row.get('Organization', 'Unknown')}: unresolved owner {name}" for name in owner.unresolved)

    return reminders, warnings


def render_slack_message(
    *,
    run_date: date,
    tracker_url: str,
    messages_searched: int,
    rows_updated: int,
    new_rows: int,
    outbound_emails_sent: int,
    duplicates_ignored: int,
    manual_reviews: list[ManualReview],
    errors: list[str],
    reminders: list[Reminder],
    sent_emails: list[SentEmail] | None = None,
    warnings: list[str] | None = None,
) -> str:
    warnings = warnings or []
    sent_emails = sent_emails or []
    lines = [
        "*PsychedelX Sponsorship Tracker Sync*",
        f"*Date:* {run_date.isoformat()}",
        f"*Tracker:* <{tracker_url}|IPN Partnerships Tracker>",
        "",
        "*Overview*",
        f"- Messages searched: {messages_searched}",
        f"- Rows updated: {rows_updated}",
        f"- New tracker rows: {new_rows}",
        f"- Outbound emails sent: {outbound_emails_sent}",
        f"- Duplicates ignored: {duplicates_ignored}",
        f"- Manual review: {len(manual_reviews)}",
        f"- Errors: {len(errors)}",
    ]

    if rows_updated == 0 and new_rows == 0 and outbound_emails_sent == 0 and not reminders:
        lines.extend(["", "No tracker updates or follow-up reminders today."])

    if sent_emails:
        lines.extend(["", "*Tracker Activity*", "_Emails sent_"])
        for item in sent_emails:
            lines.extend(
                [
                    f"- *{item.organization_or_contact}*",
                    f"  Owner: {item.owner_display}",
                    f"  Summary: {item.summary}",
                ]
            )

    if reminders:
        lines.extend(["", "*Follow-Up Reminders*"])
        for reminder in reminders:
            lines.extend(
                [
                    f"- *{reminder.organization}*",
                    f"  Owner: {reminder.owner_display}",
                    f"  Due: {reminder.due_date.isoformat()}",
                    f"  Stage: {reminder.stage}",
                    f"  Next step: {reminder.suggested_action}",
                ]
            )

    if manual_reviews:
        lines.extend(["", "*Review Needed*"])
        for item in manual_reviews:
            lines.append(f"- {item.organization_or_message}: {item.reason}")

    if warnings:
        lines.extend(["", "*Warnings*"])
        for warning in warnings:
            lines.append(f"- {warning}")

    if errors:
        lines.extend(["", "*Errors*"])
        for error in errors:
            lines.append(f"- {error}")

    return "\n".join(lines)
