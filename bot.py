# bot.py
import os
import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from sheets import append_data_bot_row  # см. ранее высланный sheets.py

# --- НАСТРОЙКИ ----------------------------------------------------------------
# Твой токен:
TOKEN = "7557353716:AAFo_rYUXohocp9N0axnoX9Nm-e0QYNsMr0"
# -----------------------------------------------------------------------------

# Инициализация бота (новый синтаксис aiogram 3.7+)
bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()

# Машина состояний для пошагового ввода метрик
class S(StatesGroup):
    dept = State()
    dom = State()
    pro = State()
    leads = State()
    b2b = State()
    services = State()


@dp.message(Command("start"))
async def start(m: Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="Добавить метрики", callback_data="add")
    await m.answer(
        "Привет! Я запишу показатели в Google Sheets → лист *data_bot*.\n"
        "Нажми кнопку и введи значения по шагам.",
        reply_markup=kb.as_markup(),
    )


@dp.callback_query(F.data == "add")
async def cb_add(c: CallbackQuery, state: FSMContext):
    await c.message.answer("Укажи номер отдела (только число). Пример: 7")
    await state.set_state(S.dept)
    await c.answer()


@dp.message(S.dept)
async def set_dept(m: Message, state: FSMContext):
    text = (m.text or "").strip()
    if not text.isdigit():
        await m.answer("Нужна цифра. Например: 3")
        return
    await state.update_data(dept=text)
    await m.answer("Ключ‑карта ДОМ (число). Пример: 1")
    await state.set_state(S.dom)


@dp.message(S.dom)
async def set_dom(m: Message, state: FSMContext):
    await state.update_data(dom=_to_int(m.text))
    await m.answer("Ключ‑карта ПРО (число). Пример: 0")
    await state.set_state(S.pro)


@dp.message(S.pro)
async def set_pro(m: Message, state: FSMContext):
    await state.update_data(pro=_to_int(m.text))
    await m.answer("Лидогенерация (число). Пример: 1")
    await state.set_state(S.leads)


@dp.message(S.leads)
async def set_leads(m: Message, state: FSMContext):
    await state.update_data(leads=_to_int(m.text))
    await m.answer("Акции для В2В (число). Пример: 0")
    await state.set_state(S.b2b)


@dp.message(S.b2b)
async def set_b2b(m: Message, state: FSMContext):
    await state.update_data(b2b=_to_int(m.text))
    await m.answer("Услуги (число). Пример: 1")
    await state.set_state(S.services)


@dp.message(S.services)
async def finalize(m: Message, state: FSMContext):
    await state.update_data(services=_to_int(m.text))
    data = await state.get_data()

    # запись в Google Sheets (лист data_bot)
    append_data_bot_row(
        department=data["dept"],            # можно "7" — в таблице станет "Отдел 7"
        key_dom=data.get("dom", 0),
        key_pro=data.get("pro", 0),
        leads=data.get("leads", 0),
        b2b=data.get("b2b", 0),
        services=data.get("services", 0),
    )

    await m.answer(
        "✅ Данные записаны.\n"
        f"Отдел {data['dept']}: ДОМ={data.get('dom',0)}, ПРО={data.get('pro',0)}, "
        f"Лиды={data.get('leads',0)}, B2B={data.get('b2b',0)}, Услуги={data.get('services',0)}"
    )
    await state.clear()


# Быстрая команда без диалога: /add отдел=7 дом=1 про=0 лиды=1 b2b=0 услуги=1
@dp.message(Command("add"))
async def quick_add(m: Message):
    import re
    t = (m.text or "").lower()

    def take(key):
        mo = re.search(rf"{key}\s*=\s*(-?\d+)", t)
        return int(mo.group(1)) if mo else 0

    dep = take("отдел")
    append_data_bot_row(
        department=str(dep),
        key_dom=take("дом"),
        key_pro=take("про"),
        leads=take("лиды"),
        b2b=take("b2b"),
        services=take("услуги"),
    )
    await m.answer("✅ Записал (команда /add).")


def _to_int(x: str) -> int:
    try:
        return int(str(x).strip())
    except Exception:
        return 0


async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
