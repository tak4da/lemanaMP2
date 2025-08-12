# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from datetime import datetime

import telebot
from telebot import types

import sheets

# === Токен бота (вшито по твоим данным) ===
BOT_TOKEN = "7557353716:AAFo_rYUXohocp9N0axnoX9Nm-e0QYNsMr0"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# Категории (как просил)
CATEGORIES = [
    ("cards_dom", "Ключ-карта ДОМ"),
    ("cards_pro", "Ключ-карта ПРО"),
    ("leads", "Лидогенерация"),
    ("b2b", "Акции для B2B"),
    ("services", "Услуги"),
]
QTY_CHOICES = ["1", "2", "3", "4", "5"]

# Память состояний
STATE = {}  # chat_id -> {...}


# ====== Клавиатуры ======
def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("📝 Внести данные"))
    kb.add(types.KeyboardButton("📅 Данные за сегодня"))
    kb.add(types.KeyboardButton("📈 Накопительно ОТ—ДО"))
    return kb


def categories_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)
    buttons = [types.InlineKeyboardButton(text=label, callback_data=f"cat::{key}") for key, label in CATEGORIES]
    kb.add(*buttons)
    return kb


def qty_kb():
    kb = types.InlineKeyboardMarkup(row_width=5)
    buttons = [types.InlineKeyboardButton(text=q, callback_data=f"qty::{q}") for q in QTY_CHOICES]
    buttons.append(types.InlineKeyboardButton(text="Ввести вручную", callback_data="qty::manual"))
    kb.add(*buttons)
    return kb


# ====== Служебное ======
def user_text(user: types.User) -> str:
    return (f"@{user.username}" if user.username else f"{user.first_name or ''} {user.last_name or ''}".strip()) or str(user.id)


def reset_state(chat_id: int):
    STATE.pop(chat_id, None)


def reset_to_start(chat_id: int):
    """Сообщение 'Данные записаны' и возврат к стартовому меню."""
    bot.send_message(chat_id, "✅ Данные записаны")
    bot.send_message(chat_id, "Привет! Это MP2-бот. Что сделать?", reply_markup=main_menu())
    reset_state(chat_id)


# ====== Команды ======
@bot.message_handler(commands=["start", "help"]) 
def cmd_start(message: types.Message):
    reset_state(message.chat.id)
    bot.send_message(message.chat.id, "Привет! Это MP2-бот. Что сделать?", reply_markup=main_menu())


# ====== Главное меню ======
@bot.message_handler(func=lambda m: m.text == "📝 Внести данные")
def menu_add(message: types.Message):
    reset_state(message.chat.id)
    bot.send_message(message.chat.id, "Выбери категорию:", reply_markup=categories_kb())


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

    STATE[message.chat.id] = {"date_from": dfrom}
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

    dfrom = STATE.get(message.chat.id, {}).get("date_from")
    if not dfrom:
        bot.send_message(message.chat.id, "Не найдена дата ОТ. Попробуй снова.", reply_markup=main_menu())
        return

    agg, total = sheets.aggregate_by_period(dfrom, dto)
    text = sheets.render_summary(agg, total, f"Сводка за период {dfrom} — {dto}")
    bot.send_message(message.chat.id, text, reply_markup=main_menu())
    reset_state(message.chat.id)


# ====== Inline callbacks ======
@bot.callback_query_handler(func=lambda c: c.data.startswith("cat::"))
def pick_category(callback: types.CallbackQuery):
    key = callback.data.split("::", 1)[1]
    label = next((lbl for k, lbl in CATEGORIES if k == key), key)
    chat_id = callback.message.chat.id

    STATE[chat_id] = {"category_key": key, "category_label": label}
    bot.answer_callback_query(callback.id, text=f"{label}")
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=callback.message.message_id,
        text=f"Сколько «{label}» сегодня?", 
        reply_markup=qty_kb()
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("qty::"))
def pick_qty(callback: types.CallbackQuery):
    choice = callback.data.split("::", 1)[1]
    chat_id = callback.message.chat.id
    label = STATE.get(chat_id, {}).get("category_label")

    if not label:
        bot.answer_callback_query(callback.id, text="Сначала выбери категорию.")
        return

    if choice == "manual":
        bot.answer_callback_query(callback.id)
        # Убираем инлайн-клавиатуру у предыдущего сообщения
        bot.edit_message_text(chat_id=chat_id, message_id=callback.message.message_id, text=f"Введи число для «{label}»: ")
        msg = bot.send_message(chat_id, "Например: 7")
        bot.register_next_step_handler(msg, handle_manual_qty, label, callback.message.message_id)
        return

    qty = int(choice)
    save_and_finish(callback, label, qty)


def handle_manual_qty(message: types.Message, label: str, to_edit_message_id: int):
    chat_id = message.chat.id
    txt = message.text.strip().replace(",", ".")
    if not txt.isdigit():
        msg = bot.send_message(chat_id, "Это не целое число. Введи количество ещё раз:")
        bot.register_next_step_handler(msg, handle_manual_qty, label, to_edit_message_id)
        return
    qty = int(txt)
    # Обновим старое сообщение (без клавиатуры), потом финальное действие
    try:
        bot.edit_message_text(chat_id=chat_id, message_id=to_edit_message_id, text=f"Ввод: {qty}")
    except Exception:
        pass
    # Сохраняем и выходим в старт
    ok, _ = sheets.append_entry(department=label, qty=qty, user=user_text(message.from_user), ref="non")
    reset_to_start(chat_id)


def save_and_finish(callback: types.CallbackQuery, label: str, qty: int):
    chat_id = callback.message.chat.id
    # Сохраняем
    ok, _ = sheets.append_entry(department=label, qty=qty, user=user_text(callback.from_user), ref="non")
    bot.answer_callback_query(callback.id)
    # Убираем инлайн-кнопки редактированием текста (без reply-клавиатур!)
    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=callback.message.message_id,
            text=f"Категория: <b>{label}</b> — {qty}"
        )
    except Exception:
        pass
    # Сообщение 'Данные записаны' и возврат к старту
    reset_to_start(chat_id)


if __name__ == "__main__":
    print("MP2-бот запущен.")
    bot.infinity_polling(skip_pending=True, allowed_updates=telebot.util.update_types)
