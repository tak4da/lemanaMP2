# sheets.py — Google Sheets integration for MP-2 bot
import os
import datetime as dt
import gspread
from google.oauth2.service_account import Credentials
import pytz
from pathlib import Path
from dotenv import load_dotenv

# Load .env from absolute path
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
SERVICE_JSON_PATH = os.getenv("SERVICE_JSON_PATH", "service_account.json")
DATA_SHEET_NAME = os.getenv("DATA_SHEET_NAME", "data_bot")
DASHBOARD_SHEET_NAME = os.getenv("DASHBOARD_SHEET_NAME", "DashBoard")
TZ_NAME = os.getenv("TZ_NAME", "Europe/Samara")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
TZ = pytz.timezone(TZ_NAME)

def _client() -> gspread.Client:
    creds = Credentials.from_service_account_file(SERVICE_JSON_PATH, scopes=SCOPES)
    return gspread.authorize(creds)

def _open_ws(name):
    gc = _client()
    sh = gc.open_by_key(SPREADSHEET_ID)
    try:
        ws = sh.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=name, rows=1000, cols=20)
    return ws

def append_data_bot_row(department, key_dom=0, key_pro=0, leads=0, b2b=0, services=0):
    ws = _open_ws(DATA_SHEET_NAME)
    now = dt.datetime.now(TZ)
    dep = f"Отдел {department}" if str(department).isdigit() else str(department)
    row = [now.strftime("%d.%m.%Y"), now.strftime("%H:%M:%S"), dep, key_dom, key_pro, leads, b2b, services]
    ws.append_row(row, value_input_option="USER_ENTERED")

def update_dashboard_today():
    data_ws = _open_ws(DATA_SHEET_NAME)
    dash_ws = _open_ws(DASHBOARD_SHEET_NAME)
    records = data_ws.get_all_values()[1:]  # skip header
    today_str = dt.datetime.now(TZ).strftime("%d.%m.%Y")
    summary = {}
    for row in records:
        if row[0] == today_str:
            dept = row[2]
            nums = list(map(int, row[3:8]))
            if dept not in summary:
                summary[dept] = [0]*5
            summary[dept] = [sum(x) for x in zip(summary[dept], nums)]
    dash_ws.clear()
    dash_ws.append_row(["Отдел", "Ключ‑карта ДОМ", "Ключ‑карта ПРО", "Лидогенерация", "Акции для B2B", "Услуги"])
    for dept, vals in summary.items():
        dash_ws.append_row([dept] + vals)

def get_summary_today():
    data_ws = _open_ws(DATA_SHEET_NAME)
    today_str = dt.datetime.now(TZ).strftime("%d.%m.%Y")
    summary = {}
    for row in data_ws.get_all_values()[1:]:
        if row[0] == today_str:
            dept = row[2]
            nums = list(map(int, row[3:8]))
            if dept not in summary:
                summary[dept] = [0]*5
            summary[dept] = [sum(x) for x in zip(summary[dept], nums)]
    return summary

def get_summary_period(start_date, end_date):
    data_ws = _open_ws(DATA_SHEET_NAME)
    summary = {}
    start_dt = dt.datetime.strptime(start_date, "%d.%m.%Y").date()
    end_dt = dt.datetime.strptime(end_date, "%d.%m.%Y").date()
    for row in data_ws.get_all_values()[1:]:
        date_val = dt.datetime.strptime(row[0], "%d.%m.%Y").date()
        if start_dt <= date_val <= end_dt:
            dept = row[2]
            nums = list(map(int, row[3:8]))
            if dept not in summary:
                summary[dept] = [0]*5
            summary[dept] = [sum(x) for x in zip(summary[dept], nums)]
    return summary
