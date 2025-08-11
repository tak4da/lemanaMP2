# sheets.py
from __future__ import annotations
import datetime as dt
from typing import Optional, Any

import gspread
from google.oauth2.service_account import Credentials
import pytz
import os

# ── НАСТРОЙКИ ────────────────────────────────────────────────────────────────
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "1VNLbyz58pWLm9wCQ5mhQar90dO4Y8kKpgRT8NfS7HVs")
SERVICE_JSON_PATH = os.getenv("SERVICE_JSON_PATH", "service_account.json")
DATA_SHEET_NAME = os.getenv("DATA_SHEET_NAME", "data_bot")
TZ_NAME = os.getenv("TZ_NAME", "Europe/Samara")  # твой часовой пояс
# ─────────────────────────────────────────────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
TZ = pytz.timezone(TZ_NAME)


def _client() -> gspread.Client:
    creds = Credentials.from_service_account_file(SERVICE_JSON_PATH, scopes=SCOPES)
    return gspread.authorize(creds)


def _open_ws():
    gc = _client()
    sh = gc.open_by_key(SPREADSHEET_ID)
    try:
        ws = sh.worksheet(DATA_SHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=DATA_SHEET_NAME, rows=1000, cols=10)
        ws.insert_row(
            ["Дата", "Время", "Отдел", "Ключ-карта ДОМ", "Ключ-карта ПРО",
             "Лидогенерация", "Акции для В2В", "Услуги"],
            1
        )
    return ws


def append_data_bot_row(
    department: str,
    key_dom: Optional[Any] = None,
    key_pro: Optional[Any] = None,
    leads: Optional[Any] = None,
    b2b: Optional[Any] = None,
    services: Optional[Any] = None,
) -> None:
    """
    Добавляет строку в конец листа data_bot.
    department можно передать как 'Отдел 7' или '7'.
    Пустые значения превращаются в 0.
    """
    ws = _open_ws()
    now = dt.datetime.now(TZ)
    date_str = now.strftime("%d.%m.%Y")
    time_str = now.strftime("%H:%M:%S")

    dep = str(department).strip()
    if dep.isdigit():
        dep = f"Отдел {dep}"

    row = [
        date_str,
        time_str,
        dep,
        _nz(key_dom),
        _nz(key_pro),
        _nz(leads),
        _nz(b2b),
        _nz(services),
    ]

    # несколько попыток — на случай коллизий API
    for _ in range(3):
        try:
            ws.append_row(row, value_input_option="USER_ENTERED")
            return
        except gspread.exceptions.APIError:
            import time as _t
            _t.sleep(0.7)
    # если совсем не повезло — бросим исключение
    ws.append_row(row, value_input_option="USER_ENTERED")


def _nz(x):
    if x is None:
        return 0
    if isinstance(x, str) and x.strip() == "":
        return 0
    return x
