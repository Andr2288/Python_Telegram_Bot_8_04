"""Точка входу: Telegram-бот нагадувань (крок 3 — структуроване /add)."""
import asyncio
import logging
import sys

from telegram import Update
from telegram.error import Conflict
from telegram.ext import Application, CommandHandler, ContextTypes

from config import BOT_TOKEN
from database.activity import log_activity
from database.db import init_db
from handlers.add import build_add_conversation_handler
from helpers.user_context import ensure_telegram_user

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger(__name__)


def _prepare_asyncio() -> None:
    """Python 3.12+ не створює loop у головному потоці; PTB run_polling цього потребує."""
    # Selector policy застаріла в 3.14+; для нових версій достатньо стандартного Proactor loop.
    if sys.platform == "win32" and sys.version_info < (3, 14):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("loop closed")
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pair = await ensure_telegram_user(update)
    if not pair:
        return
    internal_id, is_new = pair
    if is_new:
        await asyncio.to_thread(log_activity, internal_id, "register", None)
    await asyncio.to_thread(log_activity, internal_id, "start", None)
    log.info(
        "start telegram_id=%s internal_id=%s new=%s",
        update.effective_user.id,
        internal_id,
        is_new,
    )
    text = (
        "👋 Вітаю! Я бот для нагадувань.\n\n"
        "Тут ти зможеш створювати нагадування, отримувати їх у потрібний час, "
        "керувати списками та переглядати статистику.\n\n"
        "Зараз доступно:\n"
        "➕ /add — нове нагадування (текст → дата → час)\n"
        "📋 /help — усі команди\n\n"
        "<i>Далі: списки, сповіщення вчасно, повтори, часовий пояс.</i>"
    )
    await update.effective_message.reply_text(text, parse_mode="HTML")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pair = await ensure_telegram_user(update)
    if not pair:
        return
    internal_id, is_new = pair
    if is_new:
        await asyncio.to_thread(log_activity, internal_id, "register", None)
    await asyncio.to_thread(log_activity, internal_id, "help", None)
    log.info("help telegram_id=%s internal_id=%s", update.effective_user.id, internal_id)
    text = (
        "📖 <b>Довідка</b>\n\n"
        "<b>Вже працює:</b>\n"
        "/start — привітання та запис у базу\n"
        "/help — довідка (профіль у базі при першій команді)\n"
        "/add — нове нагадування (текст → дата → час), /cancel — вийти з кроків\n\n"
        "<b>Далі з’являться:</b>\n"
        "/list — активні\n"
        "/history — виконані та скасовані\n"
        "/edit — змінити нагадування\n"
        "/delete — видалити або скасувати\n"
        "/search — пошук\n"
        "/stats — статистика\n"
        "/timezone — часовий пояс\n\n"
        "Також можна писати звичайним текстом, наприклад:\n"
        "<code>нагадай завтра о 9 купити молоко</code>"
    )
    await update.effective_message.reply_text(text, parse_mode="HTML")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, Conflict):
        log.warning(
            "409 Conflict: вже є інший getUpdates (другий запуск бота, webhook або інший ПК). "
            "Залиш лише один процес з polling."
        )
        return
    log.error("Необроблена помилка", exc_info=(type(err), err, err.__traceback__))


def main() -> None:
    _prepare_asyncio()
    init_db()
    log.info("SQLite ініціалізовано")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(build_add_conversation_handler())
    app.add_error_handler(error_handler)

    log.info("Бот запущено (polling)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
