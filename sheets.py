# -*- coding: utf-8 -*-
"""
sheets.py — модуль работы с Google Sheets для MP2-бота.

Назначение:
- Подключение к таблице по сервисному аккаунту
- Запись одной строки в лист data_bot
- Агрегации за сегодня и за произвольный период ОТ—ДО
- Унифицированные функции, чтобы bot.py не работал напрямую с gspread

Важно:
- В таблице должен существовать лист с именем DATA_SHEET_NAME (по умолчанию "data_bot")
- В этом листе должна быть строка-заголовок следующего вида (в этом порядке):
    ["timestamp", "date", "time", "department", "qty", "user", "ref"]
- Форматы:
    date -> YYYY-MM-DD
    time -> HH:MM (24 часа)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple

import gspread
from google.oauth2.service_account import Credentials

# === Настройки подключения ===
SERVICE_JSON_PATH: str = os.getenv("SERVICE_JSON_PATH", "credentials/service_account.json")
SPREADSHEET_ID: str = os.getenv(
    "SPREADSHEET_ID",
    "1VNLbyz58pWLm9wCQ5mhQar90dO4Y8kKpgRT8NfS7HVs",  # ← замени при необходимости
)
DATA_SHEET_NAME: str = os.getenv("DATA_SHEET_NAME", "data_bot")

# Часовой пояс Самары (UTC+4). Если нужен другой tz — замени смещение.
SAMARA_TZ = timezone(timedelta(hours=4))

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _client() -> gspread.Client:
    """Возвращает авторизованный gspread client."""
    creds = Credentials.from_service_account_file(SERVICE_JSON_PATH, scopes=SCOPES)
    return gspread.authorize(creds)


def _open_sh():
    """Открывает книгу по SPREADSHEET_ID."""
    gc = _client()
    return gc.open_by_key(SPREADSHEET_ID)


def _get_ws():
    """Возвращает рабочий лист data_bot. Бросает ошибку, если его нет."""
    sh = _open_sh()
    try:
        ws = sh.worksheet(DATA_SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        # Если листа нет — создадим с заголовками.
        ws = sh.add_worksheet(title=DATA_SHEET_NAME, rows=2, cols=7)
        ws.append_row(["timestamp", "date", "time", "department", "qty", "user", "ref"])
    return ws


# === Публичные функции для bot.py ===
def append_entry(department: str, qty: int, user: str, ref: str = "non") -> Tuple[bool, str]:
    """
    Записывает одну строку в data_bot.
    Возвращает (ok, message). ok=True если успешно.
    """
    try:
        now = datetime.now(SAMARA_TZ)
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M")

        row = [timestamp, date_str, time_str, department, int(qty), user, ref]

        ws = _get_ws()
        ws.append_row(row, value_input_option="USER_ENTERED")
        return True, "Строка записана"
    except Exception as e:
        return False, f"Ошибка записи: {e}"


def _records() -> List[Dict[str, str]]:
    """Считывает все записи как список словарей по заголовкам."""
    ws = _get_ws()
    return ws.get_all_records()  # требует первую строку как заголовки


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def aggregate_by_period(date_from: str, date_to: str) -> Tuple[Dict[str, int], int]:
    """
    Агрегирует qty по department за период [date_from, date_to] включительно.
    Формат дат: YYYY-MM-DD
    Возвращает (словарь по отделам, общий итог).
    """
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
            dep = str(row.get("department", "")).strip() or "—"
            try:
                q = int(row.get("qty", 0))
            except Exception:
                q = 0
            agg[dep] = agg.get(dep, 0) + q
            total += q

    return agg, total


def aggregate_today() -> Tuple[Dict[str, int], int, str]:
    """Агрегирует за сегодняшний день в таймзоне Самары. Возвращает (agg, total, date_str)."""
    today = datetime.now(SAMARA_TZ).strftime("%Y-%m-%d")
    agg, total = aggregate_by_period(today, today)
    return agg, total, today


def render_summary(agg: Dict[str, int], total: int, title: str) -> str:
    """Форматирует текстовый отчёт для Telegram."""
    if not agg:
        return f"{title}\nНет данных за выбранный период."

    lines = [title, ""]
    # Отсортируем по убыванию qty
    for dep, q in sorted(agg.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"• {dep}: {q}")
    lines.append("")
    lines.append(f"ИТОГО: {total}")
    return "\n".join(lines)
