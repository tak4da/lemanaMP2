
# -*- coding: utf-8 -*-
"""
Работа с Google Sheets через gspread.
Ожидается сервисный аккаунт и файл creds.json в каталоге рядом с кодом.
Лист: data_bot. Столбцы создаём, если их нет.
"""
import gspread
from typing import Dict, Any, List

# Карта порядка столбцов в таблице
COLUMNS_ORDER = [
    "date", "time", "user", "department",
    "keycards_home", "keycards_pro",
    "leads", "b2b_deals", "services",
]

class SheetClient:
    def __init__(self, spreadsheet_id: str, worksheet_name: str = "data_bot", creds_path: str = "creds.json"):
        self.spreadsheet_id = spreadsheet_id
        self.worksheet_name = worksheet_name
        self.creds_path = creds_path
        self.gc = gspread.service_account(filename=self.creds_path)
        self.sh = self.gc.open_by_key(self.spreadsheet_id)
        try:
            self.ws = self.sh.worksheet(self.worksheet_name)
        except gspread.WorksheetNotFound:
            self.ws = self.sh.add_worksheet(title=self.worksheet_name, rows=1000, cols=20)
            self._ensure_header()

        # Проверим заголовок
        self._ensure_header()

    def _ensure_header(self):
        # Читаем первую строку
        header = self.ws.row_values(1)
        if header != COLUMNS_ORDER:
            # Перезапишем шапку (осторожно: затирает первую строку)
            self.ws.update("A1", [COLUMNS_ORDER])

    def append_row(self, row: Dict[str, Any]):
        try:
            # Собираем список значений в правильном порядке
            values: List[Any] = []
            for col in COLUMNS_ORDER:
                v = row.get(col, "")
                # Преобразуем None -> "" чтобы в таблице было пусто для "Не актуально"
                if v is None:
                    v = ""
                values.append(v)
            # Добавляем в конец
            self.ws.append_row(values, value_input_option="USER_ENTERED")
            return True, None
        except Exception as e:
            return False, str(e)
