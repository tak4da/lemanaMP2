# bot.py — MP-2 inline-flow bot (aiogram v3)
import os
import asyncio
import logging
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Load .env for BOT_TOKEN (safe for GitHub usage)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ======== External integration (Google Sheets) ========
# The function must be provided in your sheets.py
# def append_data_bot_row(department, key_dom, key_pro, leads, b2b, services): ...
from sheets import append_data_bot_row


# ======== Settings & bootstrap ========
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set. Put it into .env file: BOT_TOKEN=...")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


# ======== FSM ========
class S(StatesGroup):
    dept = State()
    dom = State()
    pro = State()
    leads = State()
    b2b = State()
    services = State()
    manual = State()  # generic manual input for any metric


# ======== Keyboards ========
def kb_start() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="Передать новые значения МП-2", callback_data="begin")
    return kb

def kb_departments() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for i in range(1, 16):
        kb.button(text=f"Отдел {i}", callback_data=f"dept:{i}")
    kb.adjust(3)  # 3 per row
    return kb

def kb_numbers(include_not_actual: bool = False) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    # numbers 0..10
    for i in range(0, 11):
        kb.button(text=str(i), callback_data=f"num:{i}")
    kb.adjust(4)  # 4-4-3 layout
    # manual input
    kb.button(text="Ввести вручную", callback_data="num:manual")
    if include_not_actual:
        kb.button(text="Не актуально", callback_data="num:na")
    kb.adjust(4)
    return kb


# ======== Helpers ========
def metric_human(metric: str) -> str:
    return {
        "dom": "Ключ‑карта ДОМ",
        "pro": "Ключ‑карта ПРО",
        "leads": "Лидогенерация",
        "b2b": "Акции для B2B",
        "services": "Услуги",
    }.get(metric, metric)

async def ask_metric(message: Message, metric: str, include_not_actual: bool = False):
    """Send question for metric with inline numbers keyboard."""
    human = metric_human(metric)
    await message.answer(
        f"Сколько <b>{human}</b> ты сегодня выполнил(а)?",
        reply_markup=kb_numbers(include_not_actual).as_markup(),
    )


# ======== Handlers ========
@dp.message(Command("start", "menu"))
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(
        "Привет, я помогу оперативно передать итоги по показателям МП‑2!\n\n"
        "Контрольное время дня:\n"
        "1 замер — 14:00\n"
        "2 замер — 18:00\n"
        "3 замер — 22:00\n\n"
        "Каждый раз передавай значения накопительно — с утра до текущей минуты суммарно.",
        reply_markup=kb_start().as_markup(),
    )


@dp.callback_query(F.data == "begin")
async def cb_begin(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.answer("Пожалуйста, выбери свой отдел:", reply_markup=kb_departments().as_markup())
    await state.set_state(S.dept)
    await c.answer()


@dp.callback_query(S.dept, F.data.startswith("dept:"))
async def cb_dept_selected(c: CallbackQuery, state: FSMContext):
    dept = c.data.split(":")[1]
    await state.update_data(dept=dept, dom=0, pro=0, leads=0, b2b=0, services=0)
    await c.message.answer(f"Ты выбрал(а) отдел: Отдел {dept}")
    # Ask DOM
    await ask_metric(c.message, "dom")
    await state.set_state(S.dom)
    await c.answer()


# ----- Numbers flow for each metric -----
async def _handle_number_or_manual(c: CallbackQuery, state: FSMContext, metric: str, next_state: State, include_not_actual: bool = False):
    payload = c.data.split(":", 1)[1]
    if payload == "manual":
        # switch to manual input
        await state.update_data(metric=metric)  # remember what we are inputting
        await c.message.answer("Введи число вручную (целое, 0 или больше).")
        await state.set_state(S.manual)
        await c.answer()
        return
    if include_not_actual and payload == "na":
        value = 0
    else:
        value = int(payload)

    await state.update_data(**{metric: value})
    human = metric_human(metric)
    await c.message.answer(f"Записано: {human} — {value} шт.")

    # move to next question
    if next_state is S.pro:
        await ask_metric(c.message, "pro")
    elif next_state is S.leads:
        await ask_metric(c.message, "leads")
    elif next_state is S.b2b:
        await ask_metric(c.message, "b2b", include_not_actual=True)
    elif next_state is S.services:
        await ask_metric(c.message, "services")
    else:
        pass
    await state.set_state(next_state)
    await c.answer()


@dp.callback_query(S.dom, F.data.startswith("num:"))
async def cb_dom_num(c: CallbackQuery, state: FSMContext):
    await _handle_number_or_manual(c, state, metric="dom", next_state=S.pro)


@dp.callback_query(S.pro, F.data.startswith("num:"))
async def cb_pro_num(c: CallbackQuery, state: FSMContext):
    await _handle_number_or_manual(c, state, metric="pro", next_state=S.leads)


@dp.callback_query(S.leads, F.data.startswith("num:"))
async def cb_leads_num(c: CallbackQuery, state: FSMContext):
    await _handle_number_or_manual(c, state, metric="leads", next_state=S.b2b, include_not_actual=False)


@dp.callback_query(S.b2b, F.data.startswith("num:"))
async def cb_b2b_num(c: CallbackQuery, state: FSMContext):
    await _handle_number_or_manual(c, state, metric="b2b", next_state=S.services, include_not_actual=True)


@dp.callback_query(S.services, F.data.startswith("num:"))
async def cb_services_num(c: CallbackQuery, state: FSMContext):
    payload = c.data.split(":", 1)[1]
    if payload == "manual":
        await state.update_data(metric="services")
        await c.message.answer("Введи число вручную (целое, 0 или больше).")
        await state.set_state(S.manual)
        await c.answer()
        return
    value = int(payload)
    await state.update_data(services=value)
    await c.message.answer(f"Записано: Услуги — {value} шт.")
    # finalize
    await finalize_and_write(c.message, state)
    await c.answer()


# ----- Manual input (for any metric) -----
@dp.message(S.manual)
async def manual_input(m: Message, state: FSMContext):
    txt = (m.text or "").strip()
    if not txt.isdigit():
        await m.answer("Нужно целое число (0 или больше). Попробуй ещё раз.")
        return
    value = int(txt)
    data = await state.get_data()
    metric: Optional[str] = data.get("metric")
    if not metric:
        await m.answer("Произошла ошибка контекста. Запусти /start.")
        await state.clear()
        return

    await state.update_data(**{metric: value})
    human = metric_human(metric)
    await m.answer(f"Записано: {human} — {value} шт.")

    # move to next metric or finalize
    if metric == "dom":
        await ask_metric(m, "pro")
        await state.set_state(S.pro)
    elif metric == "pro":
        await ask_metric(m, "leads")
        await state.set_state(S.leads)
    elif metric == "leads":
        await ask_metric(m, "b2b", include_not_actual=True)
        await state.set_state(S.b2b)
    elif metric == "b2b":
        await ask_metric(m, "services")
        await state.set_state(S.services)
    elif metric == "services":
        await finalize_and_write(m, state)


# ======== Finalization ========
async def finalize_and_write(m: Message, state: FSMContext):
    data = await state.get_data()
    dept = data.get("dept", "0")
    dom = int(data.get("dom", 0))
    pro = int(data.get("pro", 0))
    leads = int(data.get("leads", 0))
    b2b = int(data.get("b2b", 0))
    services = int(data.get("services", 0))

    await m.answer("⏳ Подождите, ваши данные записываются…")

    # write to sheets
    append_data_bot_row(
        department=str(dept),
        key_dom=dom,
        key_pro=pro,
        leads=leads,
        b2b=b2b,
        services=services,
    )

    await m.answer(
        "✅ Данные записаны.\n"
        f"Отдел {dept}: ДОМ={dom}, ПРО={pro}, Лиды={leads}, B2B={b2b}, Услуги={services}"
    )
    await state.clear()


# ======== Quick command (optional) ========
@dp.message(Command("cancel"))
async def cmd_cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Диалог сброшен. Нажми кнопку ниже, чтобы начать заново.", reply_markup=kb_start().as_markup())


# ======== Entrypoint ========
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
