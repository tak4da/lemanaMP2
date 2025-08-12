import os
import json
from datetime import datetime
import pytz
import gspread
from google.oauth2.service_account import Credentials

WORKSHEET_TITLE = "data_bot"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def _client():
    # 1) try inline JSON from env GOOGLE_SERVICE_ACCOUNT_JSON
    inline = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if inline:
        info = json.loads(inline)
        credentials = Credentials.from_service_account_info(info, scopes=SCOPES)
        return gspread.authorize(credentials)

    # 2) then try file path from env GOOGLE_APPLICATION_CREDENTIALS
    sa_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if sa_path and os.path.exists(sa_path):
        credentials = Credentials.from_service_account_file(sa_path, scopes=SCOPES)
        return gspread.authorize(credentials)

    # 3) fall back to service_account.json in cwd
    fallback = "service_account.json"
    if os.path.exists(fallback):
        credentials = Credentials.from_service_account_file(fallback, scopes=SCOPES)
        return gspread.authorize(credentials)

    raise FileNotFoundError(
        "Не найден ключ сервис-аккаунта: задайте GOOGLE_SERVICE_ACCOUNT_JSON или "
        "GOOGLE_APPLICATION_CREDENTIALS, или положите service_account.json рядом с ботом."
    )

def append_record(spreadsheet_id: str, department: str, home: int, pro: int, leads: int, b2b: int, services: int, timezone: str = "Europe/Moscow"):
    gc = _client()
    sh = gc.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(WORKSHEET_TITLE)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=WORKSHEET_TITLE, rows=1000, cols=10)
        ws.update('A1:H1', [[
            "Дата", "Время", "Отдел", "Ключ-карта ДОМ", "Ключ-карта ПРО", "Лидогенерация", "Акции для В2В", "Услуги"
        ]])

    tz = pytz.timezone(timezone)
    now = datetime.now(tz)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    row = [
        date_str,
        time_str,
        department,
        int(home),
        int(pro),
        int(leads),
        int(b2b),
        int(services),
    ]

    ws.append_row(row, value_input_option="USER_ENTERED")
    return True
