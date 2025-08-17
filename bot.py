# -*- coding: utf-8 -*-
"""
Update bot.py: все вопросы в одном редактируемом сообщении + сводка.
Ключевые моменты:
- Выбор отдела 1–15: inline-кнопки по 5 в ряд.
- Все ответы: inline-кнопки 0–3.
- Пропуски:
    * отделы 12–15: "карта ПРО" = 0, вопрос не задаётся;
    * отделы 3, 10, 11: "услуги" = 0, вопрос не задаётся.
- Состояние пользователя хранится в sessions.json и переживает рестарт.
- После окончания — сводка + кнопка "Заполнить новые".
- Команда /version покажет версию кода.
"""
import os
import json
from datetime import datetime
import pytz
import telebot
from telebot import types
from telebot.types import BotCommand

from sheets import SheetClient

# ===== Константы/настройки =====
VERSION = "v1.7-inline-editmsg-summary"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "7557353716:AAGQ5FlikZwRyH9imQLoh19XkDpPSIAxak0")
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
        BotCommand("version", "Показать версию бота"),
    ])
except Exception:
    pass

# ===== Google Sheets клиент =====
sheets = SheetClient(spreadsheet_id=SPREADSHEET_ID, worksheet_name=DATA_SHEET_NAME)

# ===== Хранилище сессий =====
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

# ===== Опрос =====
QUESTIONS = [
    ("Сколько <b>ключ-карт для дома</b> ты сегодня выдал(а)?", "keycards_home"),
    ("Сколько <b>ключ-карт ПРО</b> ты сегодня выдал(а)?", "keycards_pro"),
    ("Сколько <b>лидов</b> ты сегодня сгенерил(а)?", "leads"),
    ("Сколько <b>акций для B2B</b> ты сегодня продал(а)?", "b2b_deals"),
    ("Сколько <b>услуг</b> ты сегодня продал(а)?", "services"),
]

DEPARTMENTS_WITHOUT_SERVICES = {3, 10, 11}
DEPARTMENTS_WITHOUT_PRO = {12, 13, 14, 15}

def inline_dept_keyboard():
    mk = types.InlineKeyboardMarkup(row_width=5)
    mk.add(*[types.InlineKeyboardButton(str(i), callback_data=f"dept:{i}") for i in range(1, 16)])
    return mk

def inline_value_keyboard():
    mk = types.InlineKeyboardMarkup(row_width=4)
    mk.add(*[types.InlineKeyboardButton(str(i), callback_data=f"val:{i}") for i in range(0, 4)])
    return mk

def init_session(chat_id: str, user_id: int, username: str):
    SESSIONS[chat_id] = {
        "step": 0,
        "data": {
            "date": "", "time": "",
            "user": username or str(user_id),
            "department": None,
            "keycards_home": None,
            "keycards_pro": None,
            "leads": None,
            "b2b_deals": None,
            "services": None,
            "msg_id": None,
        }
    }
    save_sessions()

def ask_current_question(chat_id: str):
    state = SESSIONS.get(chat_id)
    if not state:
        return
    step = state["step"]
    if step < 1 or step > len(QUESTIONS):
        return
    q_text, _ = QUESTIONS[step - 1]
    msg_id = state["data"].get("msg_id")
    try:
        if msg_id:
            bot.edit_message_text(
                q_text, chat_id, msg_id,
                reply_markup=inline_value_keyboard()
            )
        else:
            msg = bot.send_message(chat_id, q_text, reply_markup=inline_value_keyboard())
            state["data"]["msg_id"] = msg.message_id
    except Exception:
        msg = bot.send_message(chat_id, q_text, reply_markup=inline_value_keyboard())
        state["data"]["msg_id"] = msg.message_id

def apply_skips(state: dict):
    dept = state["data"]["department"]
    while 1 <= state["step"] <= len(QUESTIONS):
        _, field = QUESTIONS[state["step"] - 1]
        if field == "keycards_pro" and dept in DEPARTMENTS_WITHOUT_PRO:
            state["data"]["keycards_pro"] = 0
            state["step"] += 1
            continue
        if field == "services" and dept in DEPARTMENTS_WITHOUT_SERVICES:
            state["data"]["services"] = 0
            state["step"] += 1
            continue
        break
    return state["step"] > len(QUESTIONS)

@bot.message_handler(commands=["version"])
def version_cmd(message):
    bot.reply_to(message, f"Версия бота: <b>{VERSION}</b>")

@bot.message_handler(commands=["start"])
def start_cmd(message):
    chat_id = str(message.chat.id)
    init_session(chat_id, message.from_user.id, message.from_user.username or "")
    msg = bot.send_message(
        chat_id,
        "Выбери свой <b>номер отдела</b> (1–15):",
        reply_markup=inline_dept_keyboard()
    )
    SESSIONS[chat_id]["data"]["msg_id"] = msg.message_id
    save_sessions()

@bot.message_handler(commands=["cancel"])
def cancel_cmd(message):
    chat_id = str(message.chat.id)
    if chat_id in SESSIONS:
        del SESSIONS[chat_id]
        save_sessions()
    bot.send_message(chat_id, "Опрос сброшен ❌", reply_markup=types.ReplyKeyboardRemove())

@bot.callback_query_handler(func=lambda c: c.data.startswith("dept:"))
def cb_dept(c):
    chat_id = str(c.message.chat.id)
    dept = int(c.data.split(":")[1])
    if chat_id not in SESSIONS:
        init_session(chat_id, c.from_user.id, c.from_user.username or "")
    SESSIONS[chat_id]["data"]["department"] = dept
    SESSIONS[chat_id]["step"] = 1
    save_sessions()
    bot.answer_callback_query(c.id, f"Отдел выбран: {dept}")
    bot.edit_message_text(
        f"Отдел {dept} ✅",
        chat_id,
        c.message.message_id
    )
    SESSIONS[chat_id]["data"]["msg_id"] = c.message.message_id
    done = apply_skips(SESSIONS[chat_id])
    if done:
        finish(chat_id)
    else:
        ask_current_question(chat_id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("val:"))
def cb_value(c):
    chat_id = str(c.message.chat.id)
    val = int(c.data.split(":")[1])
    if chat_id not in SESSIONS:
        bot.answer_callback_query(c.id, "Сессия не найдена, нажми /start")
        return
    state = SESSIONS[chat_id]
    step = state["step"]
    if step < 1 or step > len(QUESTIONS):
        bot.answer_callback_query(c.id, "Нет активного вопроса, нажми /start")
        return
    _, field = QUESTIONS[step - 1]
    state["data"][field] = val
    state["step"] += 1
    save_sessions()
    done = apply_skips(state)
    save_sessions()
    if done:
        finish(chat_id)
    else:
        ask_current_question(chat_id)

def finish(chat_id: str):
    state = SESSIONS.get(chat_id)
    if not state:
        return
    now = datetime.now(SAMARA_TZ)
    state["data"]["date"] = now.strftime(DATE_FORMAT)
    state["data"]["time"] = now.strftime(TIME_FORMAT)
    data_to_save = state["data"].copy()
    ok, err = sheets.append_row(data_to_save)
    summary = (
        f"<b>Отдел {state['data']['department']}</b>\n\n"
        f"Ключ-карты дом: {state['data']['keycards_home']}\n"
        f"Ключ-карты ПРО: {state['data']['keycards_pro']}\n"
        f"Лиды: {state['data']['leads']}\n"
        f"B2B акции: {state['data']['b2b_deals']}\n"
        f"Услуги: {state['data']['services']}\n\n"
        f"Дата: {state['data']['date']} {state['data']['time']}"
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Заполнить новые", callback_data="new_session"))
    try:
        bot.edit_message_text(summary, chat_id, state["data"]["msg_id"], reply_markup=kb)
    except Exception:
        msg = bot.send_message(chat_id, summary, reply_markup=kb)
        state["data"]["msg_id"] = msg.message_id
    if not ok:
        bot.send_message(chat_id, f"Ошибка записи в таблицу: {err}")
    if chat_id in SESSIONS:
        del SESSIONS[chat_id]
        save_sessions()

@bot.callback_query_handler(func=lambda c: c.data == "new_session")
def cb_new_session(c):
    chat_id = str(c.message.chat.id)
    init_session(chat_id, c.from_user.id, c.from_user.username or "")
    bot.edit_message_text(
        "Выбери свой <b>номер отдела</b> (1–15):",
        chat_id,
        c.message.message_id,
        reply_markup=inline_dept_keyboard()
    )
    SESSIONS[chat_id]["data"]["msg_id"] = c.message.message_id
    save_sessions()

if __name__ == "__main__":
    print(f"Бот запущен... {VERSION}")
    bot.infinity_polling()
