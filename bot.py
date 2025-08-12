# -*- coding: utf-8 -*-
from __future__ import annotations
import telebot
from telebot import types
import sheets

BOT_TOKEN = "7557353716:AAFo_rYUXohocp9N0axnoX9Nm-e0QYNsMr0"
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

DEPARTMENTS = [f"Отдел {i}" for i in range(1, 16)]
CATEGORIES = [
    ("cards_dom", "Ключ-карта ДОМ"),
    ("cards_pro", "Ключ-карта ПРО"),
    ("leads", "Лидогенерация"),
    ("b2b", "Акции для B2B"),
    ("services", "Услуги"),
]
QTY_CHOICES = ["1", "2", "3", "4", "5"]
STATE = {}

def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("📝 Внести данные"))
    kb.add(types.KeyboardButton("📅 Данные за сегодня"))
    kb.add(types.KeyboardButton("📈 Накопительно ОТ—ДО"))
    return kb

def departments_kb():
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(*[types.InlineKeyboardButton(d, callback_data=f"dep::{d}") for d in DEPARTMENTS])
    return kb

def categories_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(*[types.InlineKeyboardButton(lbl, callback_data=f"cat::{key}") for key, lbl in CATEGORIES])
    return kb

def qty_kb():
    kb = types.InlineKeyboardMarkup(row_width=5)
    kb.add(*[types.InlineKeyboardButton(q, callback_data=f"qty::{q}") for q in QTY_CHOICES])
    kb.add(types.InlineKeyboardButton("Ввести вручную", callback_data="qty::manual"))
    return kb

def user_text(user: types.User) -> str:
    return (f"@{user.username}" if user.username else f"{user.first_name or ''} {user.last_name or ''}".strip()) or str(user.id)

def reset_state(chat_id: int):
    STATE.pop(chat_id, None)

def reset_to_start(chat_id: int):
    bot.send_message(chat_id, "✅ Данные записаны")
    bot.send_message(chat_id, "Привет! Это MP2-бот. Что сделать?", reply_markup=main_menu())
    reset_state(chat_id)

@bot.message_handler(commands=["start", "help"])
def cmd_start(message: types.Message):
    reset_to_start(message.chat.id)

@bot.message_handler(func=lambda m: m.text == "📝 Внести данные")
def menu_add(message: types.Message):
    reset_state(message.chat.id)
    bot.send_message(message.chat.id, "Выбери отдел:", reply_markup=departments_kb())

@bot.message_handler(func=lambda m: m.text == "📅 Данные за сегодня")
def menu_today(message: types.Message):
    agg, total, date_str = sheets.aggregate_today(group_by="category")
    bot.send_message(message.chat.id, sheets.render_summary(agg, total, f"Сводка за сегодня ({date_str})"),
                     reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "📈 Накопительно ОТ—ДО")
def menu_range(message: types.Message):
    msg = bot.send_message(message.chat.id, "Введи дату ОТ (ДД.ММ.ГГГГ):")
    bot.register_next_step_handler(msg, ask_date_to)

def ask_date_to(message: types.Message):
    from datetime import datetime
    try:
        dfrom = datetime.strptime(message.text.strip(), "%d.%m.%Y").strftime("%Y-%m-%d")
    except Exception:
        msg = bot.send_message(message.chat.id, "Ошибка формата. Введи дату ОТ (ДД.ММ.ГГГГ):")
        bot.register_next_step_handler(msg, ask_date_to)
        return
    STATE[message.chat.id] = {"date_from": dfrom}
    msg = bot.send_message(message.chat.id, "Теперь дата ДО (ДД.ММ.ГГГГ):")
    bot.register_next_step_handler(msg, show_range_summary)

def show_range_summary(message: types.Message):
    from datetime import datetime
    try:
        dto = datetime.strptime(message.text.strip(), "%d.%m.%Y").strftime("%Y-%m-%d")
    except Exception:
        msg = bot.send_message(message.chat.id, "Ошибка формата. Дата ДО (ДД.ММ.ГГГГ):")
        bot.register_next_step_handler(msg, show_range_summary)
        return
    dfrom = STATE.get(message.chat.id, {}).get("date_from")
    if not dfrom:
        bot.send_message(message.chat.id, "Не найдена дата ОТ.", reply_markup=main_menu())
        return
    agg, total = sheets.aggregate_by_period(dfrom, dto, group_by="category")
    bot.send_message(message.chat.id, sheets.render_summary(agg, total, f"Сводка за период {dfrom} — {dto}"),
                     reply_markup=main_menu())
    reset_state(message.chat.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("dep::"))
def pick_department(callback: types.CallbackQuery):
    dep = callback.data.split("::", 1)[1]
    STATE[callback.message.chat.id] = {"dep": dep}
    bot.answer_callback_query(callback.id, text=f"Отдел: {dep}")
    bot.edit_message_text(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                          text=f"Отдел выбран: <b>{dep}</b>\nТеперь выбери категорию:", reply_markup=categories_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("cat::"))
def pick_category(callback: types.CallbackQuery):
    key = callback.data.split("::", 1)[1]
    label = next((lbl for k, lbl in CATEGORIES if k == key), key)
    st = STATE.get(callback.message.chat.id, {})
    st["cat_key"] = key
    st["cat_label"] = label
    STATE[callback.message.chat.id] = st
    bot.answer_callback_query(callback.id, text=label)
    dep = st.get("dep", "—")
    bot.edit_message_text(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                          text=f"Отдел: <b>{dep}</b>\nКатегория: <b>{label}</b>\nСколько?", reply_markup=qty_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("qty::"))
def pick_qty(callback: types.CallbackQuery):
    choice = callback.data.split("::", 1)[1]
    st = STATE.get(callback.message.chat.id, {})
    dep = st.get("dep")
    label = st.get("cat_label")
    if choice == "manual":
        bot.answer_callback_query(callback.id)
        bot.edit_message_text(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                              text=f"Отдел: <b>{dep}</b>\nКатегория: <b>{label}</b>\nВведи число вручную:")
        msg = bot.send_message(callback.message.chat.id, "Например: 7")
        bot.register_next_step_handler(msg, handle_manual_qty, dep, label)
        return
    qty = int(choice)
    save_and_finish(callback.message.chat.id, dep, label, qty, callback.from_user)

def handle_manual_qty(message: types.Message, dep: str, label: str):
    if not message.text.strip().isdigit():
        msg = bot.send_message(message.chat.id, "Это не число. Введи ещё раз:")
        bot.register_next_step_handler(msg, handle_manual_qty, dep, label)
        return
    qty = int(message.text.strip())
    save_and_finish(message.chat.id, dep, label, qty, message.from_user)

def save_and_finish(chat_id: int, dep: str, label: str, qty: int, user):
    sheets.append_entry(department=dep, category=label, qty=qty, user=user_text(user), ref="non")
    reset_to_start(chat_id)

if __name__ == "__main__":
    bot.infinity_polling(skip_pending=True, allowed_updates=telebot.util.update_types)
