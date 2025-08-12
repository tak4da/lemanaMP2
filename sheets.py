# -*- coding: utf-8 -*-
from __future__ import annotations
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple
import gspread
from google.oauth2.service_account import Credentials

SERVICE_JSON_PATH: str = os.getenv("SERVICE_JSON_PATH", "credentials/service_account.json")
SPREADSHEET_ID: str = "1VNLbyz58pWLm9wCQ5mhQar90dO4Y8kKpgRT8NfS7HVs"
DATA_SHEET_NAME: str = os.getenv("DATA_SHEET_NAME", "data_bot")

SAMARA_TZ = timezone(timedelta(hours=4))
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def _client() -> gspread.Client:
    creds = Credentials.from_service_account_file(SERVICE_JSON_PATH, scopes=SCOPES)
    return gspread.authorize(creds)

def _open_sh():
    return _client().open_by_key(SPREADSHEET_ID)

def _get_ws():
    sh = _open_sh()
    try:
        ws = sh.worksheet(DATA_SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=DATA_SHEET_NAME, rows=2, cols=8)
        ws.append_row(["timestamp", "date", "time", "department", "category", "qty", "user", "ref"])
    return ws

def append_entry(department: str, category: str, qty: int, user: str, ref: str = "non"):
    try:
        now = datetime.now(SAMARA_TZ)
        row = [
            now.strftime("%Y-%m-%d %H:%M:%S"),
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M"),
            department,
            category,
            int(qty),
            user,
            ref,
        ]
        _get_ws().append_row(row, value_input_option="USER_ENTERED")
        return True, "Строка записана"
    except Exception as e:
        return False, f"Ошибка записи: {e}"

def _records() -> List[Dict[str, str]]:
    return _get_ws().get_all_records()

def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")

def aggregate_by_period(date_from: str, date_to: str, group_by: str = "category") -> Tuple[Dict[str, int], int]:
    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    data = _records()
    agg: Dict[str, int] = {}
    total = 0
    for row in data:
        try:
            d = _parse_date(str(row.get("date", "")))
        except Exception:
            continue
        if df <= d <= dt:
            key = str(row.get(group_by, "")).strip() or "—"
            try:
                q = int(row.get("qty", 0))
            except Exception:
                q = 0
            agg[key] = agg.get(key, 0) + q
            total += q
    return agg, total

def aggregate_today(group_by: str = "category"):
    today = datetime.now(SAMARA_TZ).strftime("%Y-%m-%d")
    agg, total = aggregate_by_period(today, today, group_by=group_by)
    return agg, total, today

def render_summary(agg: Dict[str, int], total: int, title: str) -> str:
    if not agg:
        return f"{title}\nНет данных за выбранный период."
    lines = [title, ""]
    for key, q in sorted(agg.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"• {key}: {q}")
    lines.append("")
    lines.append(f"ИТОГО: {total}")
    return "\n".join(lines)
