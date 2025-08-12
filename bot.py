# bot.py — MP-2 bot with daily dashboard updates and summary commands
import os
import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from dotenv import load_dotenv
load_dotenv()

from sheets import append_data_bot_row, update_dashboard_today, get_summary_today, get_summary_period

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in .env")

logging.basicConfig(level=logging.INFO)
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

class S(StatesGroup):
    dept = State()
    dom = State()
    pro = State()
    leads = State()
    b2b = State()
    services = State()
    manual = State()
    period_start = State()
    period_end = State()
    metric = State()

def kb_start():
    kb = InlineKeyboardBuilder()
    kb.button(text="Передать новые значения МП-2", callback_data="begin")
    return kb

def kb_departments():
    kb = InlineKeyboardBuilder()
    for i in range(1, 16):
        kb.button(text=f"Отдел {i}", callback_data=f"dept:{i}")
    kb.adjust(3)
    return kb

def kb_numbers():
    kb = InlineKeyboardBuilder()
    for i in range(1, 6):
        kb.button(text=str(i), callback_data=f"num:{i}")
    kb.button(text="Ввести вручную", callback_data="num:manual")
    kb.adjust(3)
    return kb

def metric_human(metric: str) -> str:
    return {
        "dom": "Ключ‑карта ДОМ",
        "pro": "Ключ‑карта ПРО",
        "leads": "Лидогенерация",
        "b2b": "Акции для B2B",
        "services": "Услуги",
    }.get(metric, metric)

async def ask_metric(message: Message, metric: str):
    await message.answer(f"Сколько <b>{metric_human(metric)}</b> ты сегодня выполнил(а)?", 
                         reply_markup=kb_numbers().as_markup())

@dp.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Привет! Я помогу передать итоги по показателям МП‑2!", reply_markup=kb_start().as_markup())

@dp.callback_query(F.data == "begin")
async def cb_begin(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.answer("Выбери свой отдел:", reply_markup=kb_departments().as_markup())
    await state.set_state(S.dept)
    await c.answer()

@dp.callback_query(S.dept, F.data.startswith("dept:"))
async def cb_dept(c: CallbackQuery, state: FSMContext):
    dept = c.data.split(":")[1]
    await state.update_data(dept=dept)
    await c.message.answer(f"Ты выбрал(а) отдел {dept}")
    await ask_metric(c.message, "dom")
    await state.set_state(S.dom)
    await c.answer()

async def handle_number(c: CallbackQuery, state: FSMContext, metric: str, next_state: State):
    payload = c.data.split(":")[1]
    if payload == "manual":
        await state.update_data(metric=metric)
        await c.message.answer("Введи число вручную:")
        await state.set_state(S.manual)
        await c.answer()
        return
    value = int(payload)
    await state.update_data(**{metric: value})
    await c.message.answer(f"Записано: {metric_human(metric)} — {value} шт.")
    if next_state:
        next_metric = next_state.state.split(":")[1]
        await ask_metric(c.message, next_metric)
    await state.set_state(next_state)
    await c.answer()

@dp.callback_query(S.dom, F.data.startswith("num:"))
async def cb_dom(c: CallbackQuery, state: FSMContext):
    await handle_number(c, state, "dom", S.pro)

@dp.callback_query(S.pro, F.data.startswith("num:"))
async def cb_pro(c: CallbackQuery, state: FSMContext):
    await handle_number(c, state, "pro", S.leads)

@dp.callback_query(S.leads, F.data.startswith("num:"))
async def cb_leads(c: CallbackQuery, state: FSMContext):
    await handle_number(c, state, "leads", S.b2b)

@dp.callback_query(S.b2b, F.data.startswith("num:"))
async def cb_b2b(c: CallbackQuery, state: FSMContext):
    await handle_number(c, state, "b2b", S.services)

@dp.callback_query(S.services, F.data.startswith("num:"))
async def cb_services(c: CallbackQuery, state: FSMContext):
    payload = c.data.split(":")[1]
    if payload == "manual":
        await state.update_data(metric="services")
        await c.message.answer("Введи число вручную:")
        await state.set_state(S.manual)
        await c.answer()
        return
    value = int(payload)
    await state.update_data(services=value)
    await finalize_and_write(c.message, state)
    await c.answer()

@dp.message(S.manual)
async def manual_input(m: Message, state: FSMContext):
    if not m.text.strip().isdigit():
        await m.answer("Нужно ввести число.")
        return
    value = int(m.text.strip())
    data = await state.get_data()
    metric = data.get("metric")
    await state.update_data(**{metric: value})
    if metric == "dom":
        await ask_metric(m, "pro")
        await state.set_state(S.pro)
    elif metric == "pro":
        await ask_metric(m, "leads")
        await state.set_state(S.leads)
    elif metric == "leads":
        await ask_metric(m, "b2b")
        await state.set_state(S.b2b)
    elif metric == "b2b":
        await ask_metric(m, "services")
        await state.set_state(S.services)
    elif metric == "services":
        await finalize_and_write(m, state)

async def finalize_and_write(m: Message, state: FSMContext):
    data = await state.get_data()
    append_data_bot_row(
        department=data["dept"],
        key_dom=data.get("dom", 0),
        key_pro=data.get("pro", 0),
        leads=data.get("leads", 0),
        b2b=data.get("b2b", 0),
        services=data.get("services", 0),
    )
    update_dashboard_today()
    await m.answer("✅ Данные записаны и дашборд обновлён!")
    await state.clear()

@dp.message(Command("today"))
async def cmd_today(m: Message):
    summary = get_summary_today()
    msg = "<b>Сводка за сегодня:</b>\n" + "\n".join(f"{dept}: {vals}" for dept, vals in summary.items())
    await m.answer(msg)

@dp.message(Command("period"))
async def cmd_period_start(m: Message, state: FSMContext):
    await m.answer("Введите начальную дату в формате ДД.ММ.ГГГГ:")
    await state.set_state(S.period_start)

@dp.message(S.period_start)
async def period_start(m: Message, state: FSMContext):
    await state.update_data(start_date=m.text.strip())
    await m.answer("Введите конечную дату в формате ДД.ММ.ГГГГ:")
    await state.set_state(S.period_end)

@dp.message(S.period_end)
async def period_end(m: Message, state: FSMContext):
    data = await state.get_data()
    start = data.get("start_date")
    end = m.text.strip()
    summary = get_summary_period(start, end)
    msg = f"<b>Сводка с {start} по {end}:</b>\n" + "\n".join(f"{dept}: {vals}" for dept, vals in summary.items())
    await m.answer(msg)
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
