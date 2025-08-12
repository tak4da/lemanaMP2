import os
import json
from datetime import datetime
import pytz
import gspread
from google.oauth2.service_account import Credentials
from json.decoder import JSONDecodeError

WORKSHEET_TITLE = "data_bot"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def _credentials():
    """Return google Credentials from either env JSON or file path."""
    # 1) Try env var with raw JSON
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw:
        try:
            data = json.loads(raw)
            return Credentials.from_service_account_info(data, scopes=SCOPES)
        except JSONDecodeError as e:
            # If bad JSON in env var, ignore and try file path instead
            # This helps when the user accidentally 'echo' pastes with newlines/commands
            pass

    # 2) Try file path from env or default 'service_account.json'
    sa_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
    if not os.path.isabs(sa_path):
        sa_path = os.path.join(os.getcwd(), sa_path)
    if not os.path.exists(sa_path):
        raise FileNotFoundError(
            "Не найден ключ сервис-аккаунта. "
            "Создайте файл service_account.json рядом с bot.py "
            "или задайте GOOGLE_APPLICATION_CREDENTIALS/GOOGLE_SERVICE_ACCOUNT_JSON."
        )
    return Credentials.from_service_account_file(sa_path, scopes=SCOPES)

def _client():
    creds = _credentials()
    return gspread.authorize(creds)

def append_record(spreadsheet_id: str, department: str, home: int, pro: int, leads: int, b2b: int, services: int, timezone: str = "Europe/Moscow"):
    """Append a row to 'data_bot' with 24h time.

    Columns: Дата | Время | Отдел | Ключ-карта ДОМ | Ключ-карта ПРО | Лидогенерация | Акции для В2В | Услуги
    """
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
    from datetime import datetime
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
