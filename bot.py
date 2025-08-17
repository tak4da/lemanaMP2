# -*- coding: utf-8 -*-
"""
Бот опроса для MP-2 (Inline UI).
Ключевые моменты:
- Выбор отдела 1–15: inline-кнопки по 5 в ряд.
- Все ответы по метрикам: inline-кнопки 0–3 (без "Не актуально").
- Пропуски:
    * отделы 12–15: "карта ПРО" = 0, вопрос не задаётся;
    * отделы 3, 10, 11: "услуги" = 0, вопрос не задаётся.
- Состояние пользователя хранится в sessions.json и переживает рестарт.
- Запись в Google Sheets через SheetClient.append_row(dict) в порядке COLUMNS_ORDER.
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
VERSION = "v1.6-inline-0-3-skipfix"
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
        "step": 0,  # 0 = ждём выбор отдела; 1..len(QUESTIONS) = текущий вопрос
        "data": {
            "date": "", "time": "",
            "user": username or str(user_id),
            "department": None,
            "keycards_home": None,
            "keycards_pro": None,
            "leads": None,
            "b2b_deals": None,
            "services": None,
        }
    }
    save_sessions()

def ask_current_question(chat_id: str):
    """Показать текущий вопрос из state['step'] (1..N)."""
    state = SESSIONS.get(chat_id)
    if not state:
        return
    step = state["step"]
    if step < 1 or step > len(QUESTIONS):
        return
    q_text, _ = QUESTIONS[step - 1]
    # Дополнительно убираем любые старые reply-клавиатуры
    bot.send_message(chat_id, q_text, reply_markup=inline_value_keyboard())

def apply_skips(state: dict):
    """Применить правила пропуска к следующему(им) вопросам.
       Возвращает True, если после пропусков опрос завершён."""
    dept = state["data"]["department"]
    # Пока следующий шаг надо пропустить — проставляем 0 и двигаемся дальше.
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
        break  # дальше спрашиваем обычно

    # Проверка на завершение
    return state["step"] > len(QUESTIONS)

@bot.message_handler(commands=["version"])
def version_cmd(message):
    bot.reply_to(message, f"Версия бота: <b>{VERSION}</b>")

@bot.message_handler(commands=["start"])
def start_cmd(message):
    chat_id = str(message.chat.id)
    init_session(chat_id, message.from_user.id, message.from_user.username or "")
    # Показать выбор отдела inline
    bot.send_message(
        chat_id,
        "Выбери свой <b>номер отдела</b> (1–15):",
        reply_markup=inline_dept_keyboard()
    )

@bot.message_handler(commands=["cancel"])
def cancel_cmd(message):
    chat_id = str(message.chat.id)
    if chat_id in SESSIONS:
        del SESSIONS[chat_id]
        save_sessions()
    # Уберём любые reply-клавиатуры
    bot.send_message(chat_id, "Опрос сброшен ❌", reply_markup=types.ReplyKeyboardRemove())

@bot.callback_query_handler(func=lambda c: c.data.startswith("dept:"))
def cb_dept(c):
    chat_id = str(c.message.chat.id)
    dept = int(c.data.split(":")[1])

    # Если сессии нет — инициализируем
    if chat_id not in SESSIONS:
        init_session(chat_id, c.from_user.id, c.from_user.username or "")

    SESSIONS[chat_id]["data"]["department"] = dept
    SESSIONS[chat_id]["step"] = 1  # первый вопрос
    save_sessions()

    bot.answer_callback_query(c.id, f"Отдел выбран: {dept}")
    bot.send_message(chat_id, f"Отдел: {dept} ✅")
    # Применить возможные пропуски (на случай если первый вопрос сразу должен скипнуться — у нас такого нет, но пусть будет унифицировано)
    done = apply_skips(SESSIONS[chat_id])
    if done:
        finish(chat_id)  # маловероятно здесь
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

    # Сохраняем ответ для текущего вопроса
    _, field = QUESTIONS[step - 1]
    state["data"][field] = val
    state["step"] += 1
    save_sessions()

    # Применить пропуски к последующим шагам
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

    # Пишем именно dict (как ожидает SheetClient.append_row)
    data_to_save = state["data"].copy()
    ok, err = sheets.append_row(data_to_save)
    if not ok:
        bot.send_message(chat_id, f"Ошибка записи в таблицу: {err}")
    else:
        bot.send_message(chat_id, "Спасибо! Данные сохранены ✅")

    # Очистим сессию
    if chat_id in SESSIONS:
        del SESSIONS[chat_id]
        save_sessions()

if __name__ == "__main__":
    print(f"Бот запущен... {VERSION}")
    bot.infinity_polling()
