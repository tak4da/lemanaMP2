
# -*- coding: utf-8 -*-
"""
Бот опроса с выбором 1–3 и кнопкой "Не актуально".
Фикс: не зависает сообщение выбора отдела — мы удаляем сообщение,
с которого пришёл callback (dep/q), плюс последнее сохранённое.
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

QUESTIONS = [
    ("Сколько <b>ключ-карт для дома</b> ты сегодня выдал(а)?", "keycards_home"),
    ("Сколько <b>ключ-карт ПРО</b> ты сегодня выдал(а)?", "keycards_pro"),
    ("Сколько <b>лидов</b> ты сегодня сгенерил(а)?", "leads"),
    ("Сколько <b>акций для B2B</b> ты сегодня продал(а)?", "b2b_deals"),
    ("Сколько <b>услуг</b> ты сегодня продал(а)?", "services"),
]

def answer_keyboard(q_index: int) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("1", callback_data=f"q{q_index}:1"),
        types.InlineKeyboardButton("2", callback_data=f"q{q_index}:2"),
        types.InlineKeyboardButton("3", callback_data=f"q{q_index}:3"),
    )
    kb.row(types.InlineKeyboardButton("Не актуально", callback_data=f"q{q_index}:na"))
    return kb

def department_keyboard() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=5)
    buttons = [types.InlineKeyboardButton(str(i), callback_data=f"dep:{i}") for i in range(1, 16)]
    kb.add(*buttons)
    return kb

def restart_keyboard() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📝 ЗАПОЛНИТЬ НОВЫЕ", callback_data="start_new"))
    return kb

def start_session(user_id: str):
    SESSIONS[user_id] = {
        "department": None,
        "answers": {},
        "current_q": 0,
        "start_ts": time.time(),
        "last_msg_id": None
    }
    save_sessions()

def get_username(message):
    return message.from_user.full_name or message.from_user.username or str(message.from_user.id)

def delete_message_safe(chat_id, message_id):
    if not message_id:
        return
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass

def delete_last_message(chat_id, user_id: str):
    last_id = SESSIONS.get(user_id, {}).get("last_msg_id")
    delete_message_safe(chat_id, last_id)

@bot.message_handler(commands=['start', 'help'])
def cmd_start(message):
    user_id = str(message.from_user.id)
    start_session(user_id)
    delete_last_message(message.chat.id, user_id)
    sent = bot.send_message(
        message.chat.id,
        "Привет! 👋\nВыбери свой <b>отдел</b> (1–15):",
        reply_markup=department_keyboard()
    )
    SESSIONS[user_id]["last_msg_id"] = sent.message_id
    save_sessions()

@bot.callback_query_handler(func=lambda c: c.data == "start_new")
def on_start_new(call):
    cmd_start(call.message)

@bot.callback_query_handler(func=lambda c: c.data.startswith("dep:"))
def on_department(call):
    user_id = str(call.from_user.id)
    dep = call.data.split(":")[1]
    if user_id not in SESSIONS:
        start_session(user_id)
    SESSIONS[user_id]["department"] = dep
    SESSIONS[user_id]["current_q"] = 0

    # Удаляем и сохранённое предыдущее сообщение, и именно это сообщение с кнопками отделов
    delete_last_message(call.message.chat.id, user_id)
    delete_message_safe(call.message.chat.id, call.message.message_id)

    q_text, _ = QUESTIONS[0]
    sent = bot.send_message(
        call.message.chat.id,
        f"Отдел: <b>{dep}</b> ✅\n\n{q_text}",
        reply_markup=answer_keyboard(0)
    )
    SESSIONS[user_id]["last_msg_id"] = sent.message_id
    save_sessions()

@bot.callback_query_handler(func=lambda c: c.data.startswith("q"))
def on_answer(call):
    user_id = str(call.from_user.id)
    if user_id not in SESSIONS:
        start_session(user_id)

    try:
        left, value = call.data.split(":")
        q_index = int(left[1:])
    except Exception:
        bot.answer_callback_query(call.id, "Ошибка данных.")
        return

    SESSIONS[user_id]["answers"][q_index] = None if value == "na" else int(value)

    next_q = q_index + 1
    if next_q < len(QUESTIONS):
        SESSIONS[user_id]["current_q"] = next_q

        # Удаляем и сохранённое предыдущее, и сообщение с текущими кнопками
        delete_last_message(call.message.chat.id, user_id)
        delete_message_safe(call.message.chat.id, call.message.message_id)

        q_text, _ = QUESTIONS[next_q]
        sent = bot.send_message(
            call.message.chat.id,
            q_text,
            reply_markup=answer_keyboard(next_q)
        )
        SESSIONS[user_id]["last_msg_id"] = sent.message_id
        save_sessions()
    else:
        name = get_username(call.message)
        dep = SESSIONS[user_id]["department"]
        answers = SESSIONS[user_id]["answers"]

        now = datetime.now(SAMARA_TZ)
        row = {
            "date": now.strftime(DATE_FORMAT),
            "time": now.strftime(TIME_FORMAT),
            "user": name,
            "department": dep,
        }
        for idx, (_qtext, colname) in enumerate(QUESTIONS):
            row[colname] = answers.get(idx)

        ok, err = sheets.append_row(row)

        # Удаляем последнее сообщение-вопрос и текущее сообщение с кнопками
        delete_last_message(call.message.chat.id, user_id)
        delete_message_safe(call.message.chat.id, call.message.message_id)

        if ok:
            text = (
                "✅ Данные отправлены!\n"
                f"Отдел: <b>{dep}</b>\n"
                f"Дата: <b>{row['date']}</b>, Время: <b>{row['time']}</b>"
            )
        else:
            text = f"❌ Не удалось записать данные: {err}"

        sent = bot.send_message(call.message.chat.id, text, reply_markup=restart_keyboard())
        SESSIONS[user_id]["last_msg_id"] = sent.message_id
        save_sessions()

@bot.message_handler(commands=['cancel'])
def cmd_cancel(message):
    user_id = str(message.from_user.id)
    start_session(user_id)
    bot.reply_to(message, "Опрос сброшен. Нажми /start чтобы начать заново.")

if __name__ == "__main__":
    print("Bot is running...")
    bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=50)
