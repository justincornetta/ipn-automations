from __future__ import annotations

from datetime import date
import json
from pathlib import Path

from googleapiclient.errors import HttpError

from psychedelx_tracker.config import load_config
from psychedelx_tracker.google_auth import build_credentials
from psychedelx_tracker.gmail import SPONSOR_QUERY, build_gmail_service, fetch_message, primary_contact_email, search_messages
from psychedelx_tracker.sheets import build_sheets_service, column_index_map, read_pipeline_table, write_audit_rows
from psychedelx_tracker.slack_notify import (
    TRACKER_URL_DEFAULT,
    ManualReview,
    due_reminders,
    render_slack_message,
    load_owner_map,
)
from psychedelx_tracker.slack_post import post_message


REQUIRED_COLUMNS = {
    "Organization",
    "Contact Email",
    "IPN Point of Contact",
    "Pipeline Stage",
    "Outreach Assignment",
    "Last Updated",
    "Next Follow-Up Due",
    "Pre-2026 Communication Log",
    "Communication Log",
}


def main() -> None:
    cfg = load_config()

    auth = build_credentials(
        client_id=cfg.google_client_id,
        client_secret=cfg.google_client_secret,
        refresh_token=cfg.google_refresh_token,
    )

    gmail = build_gmail_service(auth)
    sheets = build_sheets_service(auth)

    try:
        message_ids = search_messages(gmail, user_id=cfg.google_user_email, query=SPONSOR_QUERY, max_results=50)
    except HttpError as exc:
        payload = ""
        try:
            payload = exc.content.decode("utf-8", errors="replace") if hasattr(exc, "content") and exc.content else ""
        except Exception:  # noqa: BLE001
            payload = ""
        if "accessNotConfigured" in payload or "gmail.googleapis.com" in payload and "disabled" in payload:
            raise RuntimeError(
                "Gmail API is disabled for the Google Cloud project backing this OAuth client. "
                "Enable the Gmail API (and ensure Google Sheets API is enabled too) in the same GCP project, "
                "then re-run the workflow. In Google Cloud Console: APIs & Services → Library → enable 'Gmail API'."
            ) from exc
        raise
    messages_searched = len(message_ids)

    # Read pipeline
    table = read_pipeline_table(sheets, spreadsheet_id=cfg.tracker_sheet_id, tab_name=cfg.tracker_tab_name, max_rows=1000)
    header_map = column_index_map(table.header)

    # Validate required columns (either comm log column is acceptable).
    missing = []
    for col in ("Organization", "Contact Email", "IPN Point of Contact", "Pipeline Stage", "Outreach Assignment", "Last Updated", "Next Follow-Up Due", "Notes"):
        if col not in header_map:
            missing.append(col)
    if "Pre-2026 Communication Log" not in header_map and "Communication Log" not in header_map:
        missing.append("Pre-2026 Communication Log or Communication Log")
    if missing:
        raise RuntimeError(f"Missing required columns in tracker header row: {', '.join(missing)}")

    # Build rows dicts for reminders
    rows_dicts: list[dict[str, str]] = []
    for row in table.rows:
        row_obj: dict[str, str] = {}
        for name, idx in header_map.items():
            row_obj[name] = row[idx] if idx < len(row) else ""
        rows_dicts.append(row_obj)

    owner_map = load_owner_map(Path(__file__).resolve().parents[1] / "owners.json")
    reminders, owner_warnings = due_reminders(rows_dicts, today=date.today(), owner_map=owner_map)

    # NOTE: This first GitHub Actions version focuses on reliability and reminders + audit,
    # while keeping tracker writes conservative. It will:
    # - record non-sponsor/noise items as skipped in Automation Audit,
    # - avoid modifying pipeline rows unless a future iteration adds the full matching + log-append logic.
    #
    # This prevents accidental writes until we finalize matching rules under OAuth-based Gmail reads.

    manual_reviews: list[ManualReview] = []
    errors: list[str] = []
    duplicates_ignored = 0

    # Read Automation Audit to avoid duplicates (bounded read).
    audit_values = sheets.spreadsheets().values().get(
        spreadsheetId=cfg.tracker_sheet_id,
        range=f"'{cfg.audit_tab_name}'!A2:F1000",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", []) or []
    processed_message_ids = {row[1] for row in audit_values if len(row) > 1 and row[1]}
    processed_thread_ids = {row[2] for row in audit_values if len(row) > 2 and row[2]}

    audit_rows_to_append: list[list[str]] = []
    for mid in message_ids:
        if mid in processed_message_ids:
            duplicates_ignored += 1
            continue
        try:
            msg = fetch_message(gmail, user_id=cfg.google_user_email, message_id=mid)
            if msg.thread_id in processed_thread_ids:
                duplicates_ignored += 1
                continue

            contact = primary_contact_email(msg)
            # Conservative: only audit what we saw; pipeline writes come in a follow-up PR once OAuth access is validated.
            audit_rows_to_append.append(
                [
                    date.today().isoformat(),
                    msg.message_id,
                    msg.thread_id,
                    contact or "(unresolved)",
                    "scanned_no_write",
                    "Scanned by GitHub Actions version; pipeline writes disabled until matching rules validated under OAuth.",
                ]
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Gmail read failed for message {mid}: {exc}")

    if audit_rows_to_append:
        write_audit_rows(
            sheets,
            spreadsheet_id=cfg.tracker_sheet_id,
            audit_tab_name=cfg.audit_tab_name,
            rows=audit_rows_to_append,
        )

    slack_text = render_slack_message(
        run_date=date.today(),
        tracker_url=TRACKER_URL_DEFAULT if cfg.tracker_sheet_id == "1E_kHmYj-JZ8MCDDeeJWqOPUbIqnu5AgRdC2uBfmp3fw" else f"https://docs.google.com/spreadsheets/d/{cfg.tracker_sheet_id}/edit",
        messages_searched=messages_searched,
        rows_updated=0,
        new_rows=0,
        outbound_emails_sent=0,
        duplicates_ignored=duplicates_ignored,
        manual_reviews=manual_reviews,
        errors=errors,
        reminders=reminders,
        warnings=owner_warnings,
    )

    ts = post_message(token=cfg.slack_bot_token, channel=cfg.slack_channel_id, text=slack_text)

    write_audit_rows(
        sheets,
        spreadsheet_id=cfg.tracker_sheet_id,
        audit_tab_name=cfg.audit_tab_name,
        rows=[[date.today().isoformat(), "", "", "", "slack_posted", f"Posted via GitHub Actions (ts={ts})."]],
    )

    print(json.dumps({"ok": True, "slack_ts": ts, "messages": messages_searched}))


if __name__ == "__main__":
    main()
