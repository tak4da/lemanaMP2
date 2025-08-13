
# -*- coding: utf-8 -*-
"""
Бот опроса с выбором 1–3 и кнопкой "Не актуально".
Логика:
1) Пользователь выбирает отдел (1–15).
2) Ответы на 5 вопросов, каждый: 1, 2, 3, Не актуально.
3) После завершения запись в Google Sheets (лист "data_bot").
Автор: MP2
"""
import os
import time
from datetime import datetime
import telebot
from telebot import types

from sheets import SheetClient

# ==== НАСТРОЙКИ ====
# Твой токен бота
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "7557353716:AAFo_rYUXohocp9N0axnoX9Nm-e0QYNsMr0")
# ID таблицы
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "1VNLbyz58pWLm9wCQ5mhQar90dO4Y8kKpgRT8NfS7HVs")
# Имя листа с данными
DATA_SHEET_NAME = os.getenv("DATA_SHEET_NAME", "data_bot")

# Часовой пояс пользователя: Европа/Амстердам (UTC+2 или +1 зимний). Для простоты пишем время локали сервера в 24ч формате
# Если нужно строго по Амстердаму — можно подключить pytz/zoneinfo и выставить timezone.
TIME_FORMAT = "%H:%M"  # 24-часовой формат
DATE_FORMAT = "%Y-%m-%d"

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")
sheets = SheetClient(spreadsheet_id=SPREADSHEET_ID, worksheet_name=DATA_SHEET_NAME)

# Пул сессий пользователей
SESSIONS = {}

# Вопросы и соответствующие имена столбцов
QUESTIONS = [
    ("Сколько <b>ключ-карт для дома</b> ты сегодня выдал(а)?", "keycards_home"),
    ("Сколько <b>ключ-карт ПРО</b> ты сегодня выдал(а)?", "keycards_pro"),
    ("Сколько <b>лидов</b> ты сегодня сгенерил(а)?", "leads"),
    ("Сколько <b>акций для B2B</b> ты сегодня продал(а)?", "b2b_deals"),
    ("Сколько <b>услуг</b> ты сегодня продал(а)?", "services"),
]

# Кнопки ответа 1–3 + Не актуально
def answer_keyboard(q_index: int) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=4)
    kb.add(
        types.InlineKeyboardButton("1", callback_data=f"q{q_index}:1"),
        types.InlineKeyboardButton("2", callback_data=f"q{q_index}:2"),
        types.InlineKeyboardButton("3", callback_data=f"q{q_index}:3"),
        types.InlineKeyboardButton("Не актуально", callback_data=f"q{q_index}:na"),
    )
    return kb

# Клавиатура выбора отдела 1–15
def department_keyboard() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=5)
    buttons = [types.InlineKeyboardButton(str(i), callback_data=f"dep:{i}") for i in range(1, 16)]
    kb.add(*buttons)
    return kb

def start_session(user_id):
    SESSIONS[user_id] = {
        "department": None,
        "answers": {},
        "current_q": 0,
        "start_ts": time.time(),
    }

def get_username(message):
    name = message.from_user.full_name or message.from_user.username or str(message.from_user.id)
    return name

@bot.message_handler(commands=['start', 'help'])
def cmd_start(message):
    user_id = message.from_user.id
    start_session(user_id)
    bot.send_message(
        message.chat.id,
        "Привет! 👋\nВыбери свой <b>отдел</b> (1–15):",
        reply_markup=department_keyboard()
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("dep:"))
def on_department(call):
    user_id = call.from_user.id
    dep = call.data.split(":")[1]
    if user_id not in SESSIONS:
        start_session(user_id)
    SESSIONS[user_id]["department"] = dep
    SESSIONS[user_id]["current_q"] = 0

    # Задаём первый вопрос
    q_text, _ = QUESTIONS[0]
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"Отдел: <b>{dep}</b> ✅\n\n{q_text}",
        reply_markup=answer_keyboard(0)
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("q"))
def on_answer(call):
    user_id = call.from_user.id
    if user_id not in SESSIONS:
        start_session(user_id)

    payload = call.data  # формат: q{index}:{value}
    try:
        left, value = payload.split(":")
        q_index = int(left[1:])
    except Exception:
        bot.answer_callback_query(call.id, "Ошибка данных.")
        return

    # Сохраняем ответ
    SESSIONS[user_id]["answers"][q_index] = None if value == "na" else int(value)

    # Переходим к следующему вопросу
    next_q = q_index + 1
    if next_q < len(QUESTIONS):
        SESSIONS[user_id]["current_q"] = next_q
        q_text, _ = QUESTIONS[next_q]
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"{q_text}",
            reply_markup=answer_keyboard(next_q)
        )
    else:
        # Все ответы собраны — сохраняем
        name = get_username(call.message)
        dep = SESSIONS[user_id]["department"]
        answers = SESSIONS[user_id]["answers"]

        # Формируем запись в таблицу
        now = datetime.now()
        date_str = now.strftime(DATE_FORMAT)
        time_str = now.strftime(TIME_FORMAT)

        row = {
            "date": date_str,
            "time": time_str,
            "user": name,
            "department": dep,
        }
        # добавляем все вопросы
        for idx, (_qtext, colname) in enumerate(QUESTIONS):
            row[colname] = answers.get(idx)

        # Пишем в Google Sheets
        ok, err = sheets.append_row(row)
        if ok:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="""✅ Данные отправлены!
Отдел: ...
"""
                    f"Отдел: <b>{dep}</b>
"
                    f"Дата: <b>{date_str}</b>, Время: <b>{time_str}</b>

"
                    "Если нужно — нажми /start, чтобы заполнить ещё раз."
                ),
            )
        else:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"❌ Не удалось записать данные: {err}",
            )
        # Чистим сессию
        start_session(user_id)

@bot.message_handler(commands=['cancel'])
def cmd_cancel(message):
    user_id = message.from_user.id
    start_session(user_id)
    bot.reply_to(message, "Опрос сброшен. Нажми /start чтобы начать заново.")

if __name__ == "__main__":
    print("Bot is running...")
    bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=50)
