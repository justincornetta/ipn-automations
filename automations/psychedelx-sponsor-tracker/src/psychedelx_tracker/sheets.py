from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from googleapiclient.discovery import build

from .google_auth import GoogleAuth


HEADER_ROW_INDEX_1BASED = 2


@dataclass(frozen=True)
class SheetTable:
    header: list[str]
    rows: list[list[str]]


def build_sheets_service(auth: GoogleAuth):
    return build("sheets", "v4", credentials=auth.creds, cache_discovery=False)


def get_values(service, *, spreadsheet_id: str, a1_range: str) -> list[list[str]]:
    result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=a1_range, valueRenderOption="FORMATTED_VALUE").execute()
    return result.get("values", []) or []


def update_values(service, *, spreadsheet_id: str, a1_range: str, values: list[list[Any]]) -> None:
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=a1_range,
        valueInputOption="USER_ENTERED",
        body={"values": values},
    ).execute()


def batch_update_values(service, *, spreadsheet_id: str, updates: list[tuple[str, list[list[Any]]]]) -> None:
    data = [{"range": a1_range, "values": values} for a1_range, values in updates]
    if not data:
        return
    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "USER_ENTERED", "data": data},
    ).execute()


def append_values(service, *, spreadsheet_id: str, a1_range: str, values: list[list[Any]]) -> None:
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=a1_range,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": values},
    ).execute()


def read_pipeline_table(service, *, spreadsheet_id: str, tab_name: str, max_rows: int = 1000) -> SheetTable:
    header_range = f"'{tab_name}'!A{HEADER_ROW_INDEX_1BASED}:AZ{HEADER_ROW_INDEX_1BASED}"
    header_values = get_values(service, spreadsheet_id=spreadsheet_id, a1_range=header_range)
    if not header_values or not header_values[0]:
        raise RuntimeError(f"Missing header row at {header_range}")
    header = [str(v).strip() for v in header_values[0]]

    body_range = f"'{tab_name}'!A{HEADER_ROW_INDEX_1BASED+1}:AZ{max_rows}"
    body_values = get_values(service, spreadsheet_id=spreadsheet_id, a1_range=body_range)
    rows = [[str(v) if v is not None else "" for v in row] for row in body_values]
    return SheetTable(header=header, rows=rows)


def column_index_map(header: list[str]) -> dict[str, int]:
    return {name.strip(): idx for idx, name in enumerate(header) if name and name.strip()}


def a1_column_letter(index0: int) -> str:
    # 0 -> A
    n = index0 + 1
    letters = ""
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def write_audit_rows(
    service,
    *,
    spreadsheet_id: str,
    audit_tab_name: str,
    rows: list[list[str]],
) -> None:
    # Append to the audit tab; it may be hidden.
    append_values(
        service,
        spreadsheet_id=spreadsheet_id,
        a1_range=f"'{audit_tab_name}'!A:F",
        values=rows,
    )


def today_iso() -> str:
    return date.today().isoformat()
