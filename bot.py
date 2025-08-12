# -*- coding: utf-8 -*-
"""
bot.py — Telegram-бот MP2.
Функции:
- Внести данные (выбор отдела из 15 и количество 1–5)
- Показать данные за сегодня
- Показать накопительно ОТ—ДО

Зависимости: pyTelegramBotAPI, gspread, google-auth
Переменные окружения:
- BOT_TOKEN (если не хочешь хранить токен в коде)
- SERVICE_JSON_PATH, SPREADSHEET_ID, DATA_SHEET_NAME (при необходимости)

Запуск: python3 bot.py
"""
from __future__ import annotations

import os
from datetime import datetime

import telebot
from telebot import types

import sheets

# === Токен ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "7557353716:AAFo_rYUXohocp9N0axnoX9Nm-e0QYNsMr0")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# === Константы ===
# Список 15 отделов — поправь под свои реальные названия (порядок важен только визуально)
DEPARTMENTS = [
    "Отдел 1", "Отдел 2", "Отдел 3", "Отдел 4", "Отдел 5",
    "Отдел 6", "Отдел 7", "Отдел 8", "Отдел 9", "Отдел 10",
    "Отдел 11", "Отдел 12", "Отдел 13", "Отдел 14", "Отдел 15",
]

QTY_CHOICES = ["1", "2", "3", "4", "5"]

# Хранилище состояний: chat_id -> {"dep": str, "qty": int}
STATE = {}

# === Клавиатуры ===
def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("📝 Внести данные"))
    kb.add(types.KeyboardButton("📅 Данные за сегодня"))
    kb.add(types.KeyboardButton("📈 Накопительно ОТ—ДО"))
    return kb


def departments_kb():
    kb = types.InlineKeyboardMarkup(row_width=3)
    buttons = [types.InlineKeyboardButton(text=dep, callback_data=f"dep::{dep}") for dep in DEPARTMENTS]
    kb.add(*buttons)
    return kb


def qty_kb():
    kb = types.InlineKeyboardMarkup(row_width=5)
    buttons = [types.InlineKeyboardButton(text=q, callback_data=f"qty::{q}") for q in QTY_CHOICES]
    kb.add(*buttons)
    return kb


# === Команды ===
@bot.message_handler(commands=["start", "help"])
def cmd_start(message: types.Message):
    bot.send_message(
        message.chat.id,
        "Привет! Это MP2-бот.\n\n"
        "Что сделать?",
        reply_markup=main_menu(),
    )


# === Обработка главного меню ===
@bot.message_handler(func=lambda m: m.text == "📝 Внести данные")
def menu_add(message: types.Message):
    STATE[message.chat.id] = {}
    bot.send_message(
        message.chat.id,
        "Выбери отдел из списка:",
        reply_markup=departments_kb()
    )



@bot.message_handler(func=lambda m: m.text == "📅 Данные за сегодня")
def menu_today(message: types.Message):
    agg, total, date_str = sheets.aggregate_today()
    text = sheets.render_summary(agg, total, f"Сводка за сегодня ({date_str})")
    bot.send_message(message.chat.id, text, reply_markup=main_menu())


@bot.message_handler(func=lambda m: m.text == "📈 Накопительно ОТ—ДО")
def menu_range(message: types.Message):
    msg = bot.send_message(message.chat.id, "Введи дату ОТ в формате ДД.ММ.ГГГГ:")
    bot.register_next_step_handler(msg, ask_date_to)


def ask_date_to(message: types.Message):
    date_from_txt = message.text.strip()
    try:
        dfrom = datetime.strptime(date_from_txt, "%d.%m.%Y").strftime("%Y-%m-%d")
    except Exception:
        msg = bot.send_message(message.chat.id, "Неверный формат. Введи дату ОТ в формате ДД.ММ.ГГГГ:")
        bot.register_next_step_handler(msg, ask_date_to)
        return

    # Сохраним временно
    STATE[message.chat.id] = STATE.get(message.chat.id, {})
    STATE[message.chat.id]["date_from"] = dfrom

    msg = bot.send_message(message.chat.id, "Теперь введи дату ДО в формате ДД.ММ.ГГГГ:")
    bot.register_next_step_handler(msg, show_range_summary)


def show_range_summary(message: types.Message):
    date_to_txt = message.text.strip()
    try:
        dto = datetime.strptime(date_to_txt, "%d.%m.%Y").strftime("%Y-%m-%d")
    except Exception:
        msg = bot.send_message(message.chat.id, "Неверный формат. Введи дату ДО в формате ДД.ММ.ГГГГ:")
        bot.register_next_step_handler(msg, show_range_summary)
        return

    st = STATE.get(message.chat.id, {})
    dfrom = st.get("date_from")
    if not dfrom:
        bot.send_message(message.chat.id, "Не найдена дата ОТ. Попробуй снова.", reply_markup=main_menu())
        return

    agg, total = sheets.aggregate_by_period(dfrom, dto)
    text = sheets.render_summary(agg, total, f"Сводка за период {dfrom} — {dto}")
    bot.send_message(message.chat.id, text, reply_markup=main_menu())


# === Callback-и для инлайн кнопок ===
@bot.callback_query_handler(func=lambda c: c.data.startswith("dep::"))
def pick_department(callback: types.CallbackQuery):
    dep = callback.data.split("::", 1)[1]
    chat_id = callback.message.chat.id
    STATE[chat_id] = STATE.get(chat_id, {})
    STATE[chat_id]["dep"] = dep

    bot.answer_callback_query(callback.id, text=f"Отдел: {dep}")
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=callback.message.message_id,
        text=f"Отдел выбран: <b>{dep}</b>\nТеперь выбери количество:",
        reply_markup=qty_kb(),
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("qty::"))
def pick_qty(callback: types.CallbackQuery):
    qty_text = callback.data.split("::", 1)[1]
    chat_id = callback.message.chat.id
    st = STATE.get(chat_id, {})
    dep = st.get("dep")

    if not dep:
        bot.answer_callback_query(callback.id, text="Сначала выбери отдел.")
        return

    qty = int(qty_text)

    # Кто пользователь (для записи)
    user_txt = (
        f"@{callback.from_user.username}" if callback.from_user.username else
        f"{callback.from_user.first_name or ''} {callback.from_user.last_name or ''}".strip()
    ) or str(callback.from_user.id)

    ok, msg = sheets.append_entry(department=dep, qty=qty, user=user_txt, ref="non")

    bot.answer_callback_query(callback.id)
    if ok:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=callback.message.message_id,
            text=(
                f"✅ Записано в таблицу:\n"
                f"Отдел: <b>{dep}</b>\n"
                f"Количество: <b>{qty}</b>\n\n"
                f"Ещё что-то сделать?"
            ),
            reply_markup=main_menu(),
        )
    else:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=callback.message.message_id,
            text=f"❌ Не удалось записать данные. {msg}",
            reply_markup=main_menu(),
        )


if __name__ == "__main__":
    print("MP2-бот запущен. Ожидаю команды...")
    bot.infinity_polling(skip_pending=True, allowed_updates=telebot.util.update_types)
