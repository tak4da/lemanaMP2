import os
from datetime import datetime
import pytz
import gspread
from google.oauth2.service_account import Credentials

# Таблица и лист
WORKSHEET_TITLE = "data_bot"

# Доступы — ожидаем service_account.json в корне проекта
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def _client():
    # Файл сервис-аккаунта читаем из переменной окружения или по умолчанию из service_account.json
    sa_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
    credentials = Credentials.from_service_account_file(sa_path, scopes=SCOPES)
    return gspread.authorize(credentials)

def append_record(spreadsheet_id: str, department: str, home: int, pro: int, leads: int, b2b: int, services: int, timezone: str = "Europe/Moscow"):
    """Добавляет строку в лист 'data_bot' с 24-часовым временем.

    Колонки: Дата | Время | Отдел | Ключ-карта ДОМ | Ключ-карта ПРО | Лидогенерация | Акции для В2В | Услуги
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
