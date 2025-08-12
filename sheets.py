import gspread
from google.oauth2.service_account import Credentials

# Путь к файлу сервисного аккаунта
SERVICE_JSON_PATH = "credentials/service_account.json"

# ID таблицы (из ссылки)
SPREADSHEET_ID = "1VNLbyz58pWLm9wCQ5mhQar90dO4Y8kKpgRT8NfS7HVs"

# Права для работы с таблицами и диском
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Авторизация и подключение к Google Sheets
creds = Credentials.from_service_account_file(SERVICE_JSON_PATH, scopes=SCOPES)
gc = gspread.authorize(creds)

# Открытие таблицы
sh = gc.open_by_key(SPREADSHEET_ID)

# Получение первого листа
worksheet = sh.sheet1  # или sh.worksheet("ИмяЛиста")

print(f"Подключено к таблице: {sh.title}")
