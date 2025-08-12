import logging
import os
from datetime import datetime
import pytz

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler
)

# === CONFIG ===
TOKEN = "7557353716:AAFo_rYUXohocp9N0axnoX9Nm-e0QYNsMr0"  # ваш токен бота
SPREADSHEET_ID = "1VNLbyz58pWLm9wCQ5mhQar90dO4Y8kKpgRT8NfS7HVs"  # ваш spreadsheet_id
TIMEZONE = os.getenv("BOT_TIMEZONE", "Europe/Moscow")  # можно поменять через переменную окружения

# === SHEETS ===
from sheets import append_record

# === STATES ===
DEPT, HOME, PRO, LEADS, B2B, SERVICES = range(6)

# === LOGGING ===
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# === KEYBOARDS ===
def dept_keyboard():
    # 1–15 отделов
    buttons = []
    row = []
    for i in range(1, 16):
        row.append(InlineKeyboardButton(str(i), callback_data=f"dept:{i}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)

def one_to_five_keyboard(prefix):
    buttons = [
        [
            InlineKeyboardButton("1", callback_data=f"{prefix}:1"),
            InlineKeyboardButton("2", callback_data=f"{prefix}:2"),
            InlineKeyboardButton("3", callback_data=f"{prefix}:3"),
            InlineKeyboardButton("4", callback_data=f"{prefix}:4"),
            InlineKeyboardButton("5", callback_data=f"{prefix}:5"),
        ],
        [InlineKeyboardButton("Отмена", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(buttons)

# === HELPERS ===
def now_strings():
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    return now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    text = (
        "Выберите отдел (1–15):\n"
        "Заполните форму по шагам. В любой момент можно нажать «Отмена»."
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=dept_keyboard())
    else:
        # на случай повторного запуска через кнопку
        await update.callback_query.message.reply_text(text, reply_markup=dept_keyboard())
    return DEPT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data.clear()
    await q.edit_message_text("Отменено. Наберите /start, чтобы начать заново.")
    return ConversationHandler.END

async def choose_dept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data  # dept:1..15
    _, num = data.split(":")
    context.user_data["dept"] = int(num)

    await q.edit_message_text(
        "Сколько ключ-карт для дома ты сегодня выдал(а)?",
        reply_markup=one_to_five_keyboard("home")
    )
    return HOME

async def choose_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, val = q.data.split(":")
    context.user_data["home"] = int(val)

    await q.edit_message_text(
        "Сколько ключ-карт ПРО ты сегодня выдал(а)?",
        reply_markup=one_to_five_keyboard("pro")
    )
    return PRO

async def choose_pro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, val = q.data.split(":")
    context.user_data["pro"] = int(val)

    await q.edit_message_text(
        "Сколько лидов ты сегодня сгенерил(а)?",
        reply_markup=one_to_five_keyboard("leads")
    )
    return LEADS

async def choose_leads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, val = q.data.split(":")
    context.user_data["leads"] = int(val)

    await q.edit_message_text(
        "Сколько акций для B2B ты сегодня продал(а)?",
        reply_markup=one_to_five_keyboard("b2b")
    )
    return B2B

async def choose_b2b(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, val = q.data.split(":")
    context.user_data["b2b"] = int(val)

    await q.edit_message_text(
        "Сколько услуг ты сегодня продал(а)?",
        reply_markup=one_to_five_keyboard("services")
    )
    return SERVICES

async def choose_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, val = q.data.split(":")
    context.user_data["services"] = int(val)

    # === запись в Google Sheets ===
    dept_num = context.user_data.get("dept")
    dept_name = f"Отдел {dept_num}"
    home = context.user_data.get("home", 0)
    pro = context.user_data.get("pro", 0)
    leads = context.user_data.get("leads", 0)
    b2b = context.user_data.get("b2b", 0)
    services = context.user_data.get("services", 0)

    try:
        date_str, time_str = now_strings()
        append_record(
            spreadsheet_id=SPREADSHEET_ID,
            department=dept_name,
            home=home,
            pro=pro,
            leads=leads,
            b2b=b2b,
            services=services,
            timezone=TIMEZONE,
        )
        summary = (
            f"✅ Записано в таблицу:\n"
            f"Дата: {date_str}\n"
            f"Время: {time_str}\n"
            f"Отдел: {dept_name}\n"
            f"Ключ-карта ДОМ: {home}\n"
            f"Ключ-карта ПРО: {pro}\n"
            f"Лидогенерация: {leads}\n"
            f"Акции для В2В: {b2b}\n"
            f"Услуги: {services}\n\n"
            f"Чтобы внести новую запись — /start"
        )
        await q.edit_message_text(summary)
    except Exception as e:
        logger.exception("Ошибка записи: %s", e)
        await q.edit_message_text(
            "⚠️ Произошла ошибка при записи в таблицу. Проверьте креды и доступ.\n"
            "Попробуйте снова: /start"
        )
    finally:
        context.user_data.clear()

    return ConversationHandler.END

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            DEPT: [
                CallbackQueryHandler(cancel, pattern="^cancel$"),
                CallbackQueryHandler(choose_dept, pattern="^dept:\\d+$"),
            ],
            HOME: [
                CallbackQueryHandler(cancel, pattern="^cancel$"),
                CallbackQueryHandler(choose_home, pattern="^home:[1-5]$"),
            ],
            PRO: [
                CallbackQueryHandler(cancel, pattern="^cancel$"),
                CallbackQueryHandler(choose_pro, pattern="^pro:[1-5]$"),
            ],
            LEADS: [
                CallbackQueryHandler(cancel, pattern="^cancel$"),
                CallbackQueryHandler(choose_leads, pattern="^leads:[1-5]$"),
            ],
            B2B: [
                CallbackQueryHandler(cancel, pattern="^cancel$"),
                CallbackQueryHandler(choose_b2b, pattern="^b2b:[1-5]$"),
            ],
            SERVICES: [
                CallbackQueryHandler(cancel, pattern="^cancel$"),
                CallbackQueryHandler(choose_services, pattern="^services:[1-5]$"),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )

    application.add_handler(conv)

    # safety: catch-all for stray presses of "Отмена"
    application.add_handler(CallbackQueryHandler(cancel, pattern="^cancel$"))

    application.run_polling(allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    main()
