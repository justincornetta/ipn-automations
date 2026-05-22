from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from googleapiclient.errors import HttpError

from psychedelx_tracker.config import load_config
from psychedelx_tracker.google_auth import build_credentials
from psychedelx_tracker.gmail import SPONSOR_QUERY, build_gmail_service, fetch_message, primary_contact_email, search_messages
from psychedelx_tracker.sheets import (
    a1_column_letter,
    append_values,
    batch_update_values,
    build_sheets_service,
    column_index_map,
    read_pipeline_table,
    write_audit_rows,
)
from psychedelx_tracker.slack_notify import TRACKER_URL_DEFAULT, ManualReview, due_reminders, load_owner_map, render_slack_message
from psychedelx_tracker.slack_post import post_message
from psychedelx_tracker.text_utils import clean_whitespace, safe_summary
from psychedelx_tracker.tracker_policy import Direction, add_business_days, build_log_line, classify_message, should_create_new_tracker_row


SKIP_FROM_DOMAINS = {
    "docs.google.com",
    "calendar.google.com",
}


@dataclass(frozen=True)
class RowRef:
    row_number: int
    values: dict[str, str]


def _is_noise_sender(email_addr: str) -> bool:
    email_addr = (email_addr or "").lower().strip()
    if not email_addr:
        return False
    domain = email_addr.split("@")[-1]
    return domain in SKIP_FROM_DOMAINS or email_addr.endswith("@docs.google.com") or "comments-noreply@docs.google.com" in email_addr


def _comm_log_column(header_map: dict[str, int]) -> str:
    return "Pre-2026 Communication Log" if "Pre-2026 Communication Log" in header_map else "Communication Log"


def _row_updates_for_message(
    *,
    tab_name: str,
    header_map: dict[str, int],
    row_number: int,
    row: dict[str, str],
    direction: Direction,
    message_date: date,
    summary_text: str,
    classification_text: str,
) -> tuple[list[tuple[str, list[list[str]]]], bool, bool, str]:
    """
    Returns (updates, is_initial_outbound, stage_changed, reason)
    updates: list of (A1_range, [[value]]) entries suitable for batch_update_values.
    """
    comm_col = _comm_log_column(header_map)
    existing_log = (row.get(comm_col, "") or "").strip()
    stage_before = (row.get("Pipeline Stage", "") or "").strip()
    first_contacted_before = (row.get("First Contacted", "") or "").strip()

    is_initial_outbound = (
        direction == Direction.OUTBOUND
        and stage_before == "Lead Generation"
        and not first_contacted_before
        and not existing_log
    )

    classification = classify_message(classification_text, direction=direction, current_stage=stage_before)
    stage_after = stage_before
    next_due_value: str | None = None
    next_step_text = "None."
    stage_changed = False

    if classification.stage:
        stage_after = classification.stage
        stage_changed = stage_after != stage_before

    if classification.follow_up_days:
        next_due_value = add_business_days(message_date, classification.follow_up_days).isoformat()
        next_step_text = "Follow up in 2 business days."

    if classification.clear_follow_up and stage_after in ("Closed Won", "Closed Lost"):
        next_due_value = ""
        next_step_text = "None."

    log_line = build_log_line(
        message_date=message_date,
        direction=direction,
        contact_or_org=row.get("Organization", "").strip() or "Unknown",
        summary=summary_text,
        next_step=next_step_text,
    )

    updates: list[tuple[str, list[list[str]]]] = []

    if log_line and log_line not in existing_log:
        new_log_value = (existing_log + "\n" + log_line).strip() if existing_log else log_line
        col_letter = a1_column_letter(header_map[comm_col])
        updates.append((f"'{tab_name}'!{col_letter}{row_number}", [[new_log_value]]))

    # Last Updated always set to the message date (most recent processed message wins).
    col_letter = a1_column_letter(header_map["Last Updated"])
    updates.append((f"'{tab_name}'!{col_letter}{row_number}", [[message_date.isoformat()]]))

    if direction == Direction.OUTBOUND and not first_contacted_before and "First Contacted" in header_map:
        col_letter = a1_column_letter(header_map["First Contacted"])
        updates.append((f"'{tab_name}'!{col_letter}{row_number}", [[message_date.isoformat()]]))

    if stage_changed:
        col_letter = a1_column_letter(header_map["Pipeline Stage"])
        updates.append((f"'{tab_name}'!{col_letter}{row_number}", [[stage_after]]))

    if next_due_value is not None:
        col_letter = a1_column_letter(header_map["Next Follow-Up Due"])
        updates.append((f"'{tab_name}'!{col_letter}{row_number}", [[next_due_value]]))

    did_change = bool(updates)
    return updates, is_initial_outbound, stage_changed, classification.reason


def main() -> None:
    cfg = load_config()
    tz = ZoneInfo("America/New_York")

    auth = build_credentials(
        client_id=cfg.google_client_id,
        client_secret=cfg.google_client_secret,
        refresh_token=cfg.google_refresh_token,
    )

    gmail = build_gmail_service(auth)
    sheets = build_sheets_service(auth)

    # Gmail search window
    try:
        message_ids = search_messages(gmail, user_id=cfg.google_user_email, query=SPONSOR_QUERY, max_results=200)
    except HttpError as exc:
        payload = ""
        try:
            payload = exc.content.decode("utf-8", errors="replace") if hasattr(exc, "content") and exc.content else ""
        except Exception:  # noqa: BLE001
            payload = ""
        if "accessNotConfigured" in payload or ("gmail.googleapis.com" in payload and "disabled" in payload):
            raise RuntimeError(
                "Gmail API is disabled for the Google Cloud project backing this OAuth client. "
                "Enable the Gmail API (and ensure Google Sheets API is enabled too) in the same GCP project, "
                "then re-run the workflow. In Google Cloud Console: APIs & Services → Library → enable 'Gmail API'."
            ) from exc
        raise

    messages_searched = len(message_ids)

    # Read pipeline
    table = read_pipeline_table(
        sheets,
        spreadsheet_id=cfg.tracker_sheet_id,
        tab_name=cfg.tracker_tab_name,
        max_rows=1000,
    )
    header_map = column_index_map(table.header)

    required = [
        "Organization",
        "Contact Email",
        "IPN Point of Contact",
        "Pipeline Stage",
        "Prospect Rating",
        "Outreach Assignment",
        "First Contacted",
        "Last Updated",
        "Next Follow-Up Due",
        "Notes",
    ]
    missing = [col for col in required if col not in header_map]
    if "Pre-2026 Communication Log" not in header_map and "Communication Log" not in header_map:
        missing.append("Pre-2026 Communication Log or Communication Log")
    if missing:
        raise RuntimeError(f"Missing required columns in tracker header row: {', '.join(missing)}")

    comm_col = _comm_log_column(header_map)

    # Convert sheet rows to dicts with row numbers (row 3+)
    rows: list[RowRef] = []
    for idx, row_values in enumerate(table.rows):
        row_number = 3 + idx
        row_dict: dict[str, str] = {}
        for name, col_idx in header_map.items():
            row_dict[name] = row_values[col_idx] if col_idx < len(row_values) else ""
        rows.append(RowRef(row_number=row_number, values=row_dict))

    owner_map = load_owner_map(Path(__file__).resolve().parents[1] / "owners.json")
    reminders, _owner_warnings = due_reminders([r.values for r in rows], today=date.today(), owner_map=owner_map)

    # Read Automation Audit to avoid duplicates
    audit_values = (
        sheets.spreadsheets()
        .values()
        .get(
            spreadsheetId=cfg.tracker_sheet_id,
            range=f"'{cfg.audit_tab_name}'!A2:F2000",
            valueRenderOption="FORMATTED_VALUE",
        )
        .execute()
        .get("values", [])
        or []
    )
    processed_message_ids = {r[1] for r in audit_values if len(r) > 1 and r[1]}
    processed_thread_ids = {r[2] for r in audit_values if len(r) > 2 and r[2]}

    # Build indexes for matching
    email_to_index: dict[str, int] = {}
    domain_to_indexes: dict[str, list[int]] = {}
    for i, row in enumerate(rows):
        email = (row.values.get("Contact Email", "") or "").strip().lower()
        if not email:
            continue
        email_to_index[email] = i
        domain = email.split("@")[-1]
        domain_to_indexes.setdefault(domain, []).append(i)

    manual_reviews: list[ManualReview] = []
    errors: list[str] = []
    audit_rows_to_append: list[list[str]] = []

    # Summary counters (new-only)
    new_initial_outbound = 0
    new_followup_outbound = 0
    new_inbound = 0
    rows_updated = 0
    new_tracker_rows = 0

    for mid in message_ids:
        try:
            msg = fetch_message(gmail, user_id=cfg.google_user_email, message_id=mid)

            if msg.message_id in processed_message_ids or msg.thread_id in processed_thread_ids:
                continue

            if _is_noise_sender(msg.from_email):
                audit_rows_to_append.append([date.today().isoformat(), msg.message_id, msg.thread_id, "(noise)", "skipped_noise", "Auto-notification; ignored."])
                continue

            direction = Direction.OUTBOUND if msg.is_outbound else Direction.INBOUND
            message_date = msg.date_utc.astimezone(tz).date()

            contact_email = primary_contact_email(msg)
            if not contact_email:
                manual_reviews.append(ManualReview("(unresolved)", "Could not resolve counterparty email."))
                audit_rows_to_append.append([date.today().isoformat(), msg.message_id, msg.thread_id, "(unresolved)", "manual_review", "Could not resolve counterparty email."])
                continue

            classification_text = clean_whitespace(f"{msg.subject}\n{msg.snippet}")

            # Find row match
            row_index = email_to_index.get(contact_email)
            if row_index is None:
                domain = contact_email.split("@")[-1]
                candidates = domain_to_indexes.get(domain, [])
                if len(candidates) == 1:
                    row_index = candidates[0]
                elif len(candidates) > 1:
                    manual_reviews.append(ManualReview(contact_email, f"Multiple tracker rows match domain {domain}; skipped."))
                    audit_rows_to_append.append([date.today().isoformat(), msg.message_id, msg.thread_id, domain, "manual_review", "Multiple domain matches; skipped."])
                    continue

            if row_index is None:
                # Create new row only for clear outbound sponsor outreach
                if not should_create_new_tracker_row(classification_text, direction=direction, recipient_email=contact_email):
                    audit_rows_to_append.append([date.today().isoformat(), msg.message_id, msg.thread_id, contact_email, "skipped_non_sponsor", "Unmatched and not clear sponsor outreach; no row created."])
                    continue

                org = contact_email.split("@")[-1].split(".")[0].title()
                sender_name = (msg.from_email.split("@", 1)[0].title() if msg.from_email else "Justin") or "Justin"
                next_due = add_business_days(message_date, 2)

                log_line = build_log_line(
                    message_date=message_date,
                    direction=direction,
                    contact_or_org=f"{org} / {contact_email}",
                    summary="Outbound sponsorship/partnership outreach sent.",
                    next_step="Follow up in 2 business days if no reply.",
                )

                new_row: dict[str, str] = {col: "" for col in table.header if col}
                new_row["Organization"] = org
                new_row["Contact Email"] = contact_email
                new_row["Source of Lead"] = "Auto-created from Gmail outreach"
                new_row["IPN Point of Contact"] = sender_name
                new_row["Pipeline Stage"] = "Contacted"
                new_row["Prospect Rating"] = "4. Unknown"
                new_row["Outreach Assignment"] = sender_name
                new_row["First Contacted"] = message_date.isoformat()
                new_row["Last Updated"] = message_date.isoformat()
                new_row["Next Follow-Up Due"] = next_due.isoformat()
                new_row[comm_col] = log_line
                new_row["Notes"] = "Auto-created by Gmail tracker sync; review details."

                append_values(
                    sheets,
                    spreadsheet_id=cfg.tracker_sheet_id,
                    a1_range=f"'{cfg.tracker_tab_name}'!A:AZ",
                    values=[[new_row.get(col, "") for col in table.header]],
                )
                new_tracker_rows += 1
                new_initial_outbound += 1
                audit_rows_to_append.append([date.today().isoformat(), msg.message_id, msg.thread_id, org, "created_row", f"Auto-created row; follow-up due {next_due.isoformat()}"])
                continue

            rowref = rows[row_index]
            row = rowref.values

            summary_text = safe_summary(msg.subject, msg.snippet)
            updates, is_initial, _stage_changed, reason = _row_updates_for_message(
                tab_name=cfg.tracker_tab_name,
                header_map=header_map,
                row_number=rowref.row_number,
                row=row,
                direction=direction,
                message_date=message_date,
                summary_text=summary_text,
                classification_text=classification_text,
            )

            if direction == Direction.OUTBOUND:
                if is_initial:
                    new_initial_outbound += 1
                else:
                    new_followup_outbound += 1
            else:
                new_inbound += 1

            if updates:
                batch_update_values(sheets, spreadsheet_id=cfg.tracker_sheet_id, updates=updates)
                rows_updated += 1
                audit_rows_to_append.append([date.today().isoformat(), msg.message_id, msg.thread_id, row.get("Organization", "") or contact_email, "updated_row", reason])
            else:
                audit_rows_to_append.append([date.today().isoformat(), msg.message_id, msg.thread_id, row.get("Organization", "") or contact_email, "no_change", "No updates required."])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Message {mid}: {exc}")

    if audit_rows_to_append:
        write_audit_rows(
            sheets,
            spreadsheet_id=cfg.tracker_sheet_id,
            audit_tab_name=cfg.audit_tab_name,
            rows=audit_rows_to_append,
        )

    tracker_update = rows_updated + new_tracker_rows

    slack_text = render_slack_message(
        run_date=date.today(),
        tracker_url=TRACKER_URL_DEFAULT
        if cfg.tracker_sheet_id == "1E_kHmYj-JZ8MCDDeeJWqOPUbIqnu5AgRdC2uBfmp3fw"
        else f"https://docs.google.com/spreadsheets/d/{cfg.tracker_sheet_id}/edit",
        new_initial_outbound=new_initial_outbound,
        new_followup_outbound=new_followup_outbound,
        new_inbound=new_inbound,
        tracker_update=tracker_update,
        messages_searched=messages_searched,
        rows_updated=rows_updated,
        new_rows=new_tracker_rows,
        manual_reviews=manual_reviews,
        errors=errors,
        reminders=reminders,
    )

    try:
        ts = post_message(token=cfg.slack_bot_token, channel=cfg.slack_channel_id, text=slack_text)
        write_audit_rows(
            sheets,
            spreadsheet_id=cfg.tracker_sheet_id,
            audit_tab_name=cfg.audit_tab_name,
            rows=[[date.today().isoformat(), "", "", "", "slack_posted", f"Posted via GitHub Actions (ts={ts})."]],
        )
    except Exception as exc:  # noqa: BLE001
        write_audit_rows(
            sheets,
            spreadsheet_id=cfg.tracker_sheet_id,
            audit_tab_name=cfg.audit_tab_name,
            rows=[[date.today().isoformat(), "", "", "", "slack_error", f"Slack post failed: {exc}"]],
        )
        raise

    print(json.dumps({"ok": True, "slack_ts": ts, "messages": messages_searched}))


if __name__ == "__main__":
    main()

