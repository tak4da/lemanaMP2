# -*- coding: utf-8 -*-
"""
Бот опроса: выбор 0–3.
Изменения:
1) Кнопки отделов (1–15) в виде Inline-кнопок по 5 в ряд (квадратные).
2) Кнопки выбора показателей тоже Inline-кнопки (0–3).
3) Для отделов 12–15 пропускается "карта ПРО" (ставится 0).
4) Для отделов 3, 10, 11 пропускается "услуги" (ставится 0).
5) Состояние сохраняется в sessions.json.
"""
import os
import json
from datetime import datetime
import pytz
import telebot
from telebot import types
from telebot.types import BotCommand

from sheets import SheetClient

# ==== НАСТРОЙКИ ====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "7557353716:AAFo_rYUXohocp9N0axnoX9Nm-e0QYNsMr0")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "1VNLbyz58pWLm9wCQ5mhQar90dO4Y8kKpgRT8NfS7HVs")
DATA_SHEET_NAME = os.getenv("DATA_SHEET_NAME", "data_bot")
SESSIONS_FILE = "sessions.json"
SAMARA_TZ = pytz.timezone("Europe/Samara")

TIME_FORMAT = "%H:%M"
DATE_FORMAT = "%Y-%m-%d"

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")

try:
    bot.set_my_commands([
        BotCommand("start", "Начать опрос"),
        BotCommand("cancel", "Сбросить опрос"),
    ])
except Exception:
    pass

sheets = SheetClient(spreadsheet_id=SPREADSHEET_ID, worksheet_name=DATA_SHEET_NAME)

def load_sessions():
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_sessions():
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(SESSIONS, f, ensure_ascii=False)

SESSIONS = load_sessions()

# Вопросы и имена столбцов
QUESTIONS = [
    ("Сколько <b>ключ-карт для дома</b> ты сегодня выдал(а)?", "keycards_home"),
    ("Сколько <b>ключ-карт ПРО</b> ты сегодня выдал(а)?", "keycards_pro"),
    ("Сколько <b>лидов</b> ты сегодня сгенерил(а)?", "leads"),
    ("Сколько <b>акций для B2B</b> ты сегодня продал(а)?", "b2b_deals"),
    ("Сколько <b>услуг</b> ты сегодня продал(а)?", "services"),
]

# Отделы, где услуги всегда = 0
DEPARTMENTS_WITHOUT_SERVICES = [3, 10, 11]
# Отделы, где карты ПРО всегда = 0
DEPARTMENTS_WITHOUT_PRO = [12, 13, 14, 15]

def get_value_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=4)
    buttons = [
        types.InlineKeyboardButton("0", callback_data="val_0"),
        types.InlineKeyboardButton("1", callback_data="val_1"),
        types.InlineKeyboardButton("2", callback_data="val_2"),
        types.InlineKeyboardButton("3", callback_data="val_3"),
    ]
    markup.add(*buttons)
    return markup

@bot.message_handler(commands=["start"])
def start(message):
    chat_id = str(message.chat.id)
    SESSIONS[chat_id] = {
        "step": 0,
        "data": {"department": None}
    }
    save_sessions()

    # создаём inline-клавиатуру с отделами 1–15 (по 5 в ряд)
    markup = types.InlineKeyboardMarkup(row_width=5)
    buttons = [types.InlineKeyboardButton(str(i), callback_data=f"dept_{i}") for i in range(1, 16)]
    markup.add(*buttons)

    bot.send_message(chat_id, "Выбери свой <b>номер отдела</b> (1–15):", reply_markup=markup)

@bot.message_handler(commands=["cancel"])
def cancel(message):
    chat_id = str(message.chat.id)
    if chat_id in SESSIONS:
        del SESSIONS[chat_id]
        save_sessions()
    bot.send_message(chat_id, "Опрос сброшен ❌")

# обработка выбора отдела
@bot.callback_query_handler(func=lambda call: call.data.startswith("dept_"))
def handle_department(call):
    chat_id = str(call.message.chat.id)
    dept = int(call.data.split("_")[1])

    if chat_id not in SESSIONS:
        SESSIONS[chat_id] = {"step": 0, "data": {}}

    state = SESSIONS[chat_id]
    state["data"]["department"] = dept
    state["step"] = 1
    save_sessions()

    bot.send_message(chat_id, f"Отдел: {dept} ✅\n{QUESTIONS[0][0]}", reply_markup=get_value_keyboard())

# обработка значений 0–3
@bot.callback_query_handler(func=lambda call: call.data.startswith("val_"))
def handle_value(call):
    chat_id = str(call.message.chat.id)
    val = int(call.data.split("_")[1])

    if chat_id not in SESSIONS:
        bot.send_message(chat_id, "Начни заново: /start")
        return

    state = SESSIONS[chat_id]
    step = state["step"]
    current_question, field_name = QUESTIONS[step - 1]
    dept = state["data"]["department"]

    # сохраняем значение
    state["data"][field_name] = val

    # проверка для карт ПРО (пропуск)
    if field_name == "keycards_home" and dept in DEPARTMENTS_WITHOUT_PRO:
        state["data"]["keycards_pro"] = 0
        step += 1

    # проверка для услуг (пропуск)
    if field_name == "b2b_deals" and dept in DEPARTMENTS_WITHOUT_SERVICES:
        state["data"]["services"] = 0
        finish(chat_id, state)
        return

    # шаги дальше
    if step >= len(QUESTIONS):
        finish(chat_id, state)
    else:
        state["step"] = step + 1
        save_sessions()
        next_q, _ = QUESTIONS[state["step"] - 1]

        # проверка для карт ПРО на этом этапе
        if QUESTIONS[state["step"] - 1][1] == "keycards_pro" and dept in DEPARTMENTS_WITHOUT_PRO:
            state["data"]["keycards_pro"] = 0
            state["step"] += 1
            save_sessions()
            next_q, _ = QUESTIONS[state["step"] - 1]

        # проверка для услуг на этом этапе
        if QUESTIONS[state["step"] - 1][1] == "services" and dept in DEPARTMENTS_WITHOUT_SERVICES:
            state["data"]["services"] = 0
            finish(chat_id, state)
            return

        bot.send_message(chat_id, next_q, reply_markup=get_value_keyboard())

def finish(chat_id, state):
    data = state["data"]
    now = datetime.now(SAMARA_TZ)
    data["date"] = now.strftime(DATE_FORMAT)
    data["time"] = now.strftime(TIME_FORMAT)
    sheets.append_row(list(data.values()))
    del SESSIONS[chat_id]
    save_sessions()
    bot.send_message(chat_id, "Спасибо! Данные сохранены ✅")

if __name__ == "__main__":
    print("Бот запущен...")
    bot.infinity_polling()
