# -*- coding: utf-8 -*-
"""
Бот опроса: выбор 0–3.
Изменения:
1) Кнопки отделов (1–15) при старте.
2) Кнопки выбора для показателей только 0–3.
3) Для отделов 12–15 пропускается "карта ПРО" (ставится 0).
4) Для отделов 3, 10, 11 пропускается "услуги" (ставится 0).
"""
import os
import time
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

def get_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    buttons = ["0", "1", "2", "3"]
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

    # создаём клавиатуру с отделами 1–15
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = [str(i) for i in range(1, 16)]
    for i in range(0, len(buttons), 5):
        markup.add(*buttons[i:i+5])

    bot.send_message(chat_id, "Выбери свой <b>номер отдела</b> (1–15):", reply_markup=markup)

@bot.message_handler(commands=["cancel"])
def cancel(message):
    chat_id = str(message.chat.id)
    if chat_id in SESSIONS:
        del SESSIONS[chat_id]
        save_sessions()
    bot.send_message(chat_id, "Опрос сброшен ❌")

@bot.message_handler(func=lambda msg: True)
def handler(message):
    chat_id = str(message.chat.id)
    text = message.text.strip()

    if chat_id not in SESSIONS:
        bot.send_message(chat_id, "Нажми /start чтобы начать.")
        return

    state = SESSIONS[chat_id]
    step = state["step"]

    # шаг 0: выбор отдела
    if step == 0:
        try:
            dept = int(text)
            if 1 <= dept <= 15:
                state["data"]["department"] = dept
                state["step"] = 1
                save_sessions()
                bot.send_message(chat_id, QUESTIONS[0][0], reply_markup=get_keyboard())
            else:
                bot.send_message(chat_id, "Введи номер отдела от 1 до 15.")
        except ValueError:
            bot.send_message(chat_id, "Введи корректный номер отдела.")
        return

    # шаги 1+
    current_question, field_name = QUESTIONS[step - 1]

    # проверка для карт ПРО
    if field_name == "keycards_pro" and state["data"]["department"] in DEPARTMENTS_WITHOUT_PRO:
        state["data"]["keycards_pro"] = 0
        state["step"] += 1
        save_sessions()
        next_q, _ = QUESTIONS[state["step"] - 1]
        bot.send_message(chat_id, next_q, reply_markup=get_keyboard())
        return

    # проверка для услуг
    if field_name == "services" and state["data"]["department"] in DEPARTMENTS_WITHOUT_SERVICES:
        state["data"]["services"] = 0
        finish(chat_id, state)
        return

    if text not in ["0", "1", "2", "3"]:
        bot.send_message(chat_id, "Выбирай только кнопки 0–3.")
        return

    state["data"][field_name] = int(text)

    if step == len(QUESTIONS):
        finish(chat_id, state)
    else:
        state["step"] += 1
        save_sessions()
        next_q, _ = QUESTIONS[state["step"] - 1]

        # проверяем, нужно ли пропускать карты ПРО или услуги
        if QUESTIONS[state["step"] - 1][1] == "keycards_pro" and state["data"]["department"] in DEPARTMENTS_WITHOUT_PRO:
            state["data"]["keycards_pro"] = 0
            state["step"] += 1
            save_sessions()
            next_q, _ = QUESTIONS[state["step"] - 1]

        if QUESTIONS[state["step"] - 1][1] == "services" and state["data"]["department"] in DEPARTMENTS_WITHOUT_SERVICES:
            state["data"]["services"] = 0
            finish(chat_id, state)
            return

        bot.send_message(chat_id, next_q, reply_markup=get_keyboard())

def finish(chat_id, state):
    data = state["data"]
    now = datetime.now(SAMARA_TZ)
    data["date"] = now.strftime(DATE_FORMAT)
    data["time"] = now.strftime(TIME_FORMAT)
    sheets.append_row(list(data.values()))
    del SESSIONS[chat_id]
    save_sessions()
    bot.send_message(chat_id, "Спасибо! Данные сохранены ✅", reply_markup=types.ReplyKeyboardRemove())

if __name__ == "__main__":
    print("Бот запущен...")
    bot.infinity_polling()
