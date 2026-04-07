"""Точка входу: Telegram-бот нагадувань (крок 1 — старт, довідка, БД, логи)."""
import asyncio
import logging
import sys

from telegram import Update
from telegram.error import Conflict
from telegram.ext import Application, CommandHandler, ContextTypes

from config import BOT_TOKEN
from database.db import init_db

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
    if update.effective_user:
        log.info("start user_id=%s", update.effective_user.id)
    text = (
        "👋 Вітаю! Я бот для нагадувань.\n\n"
        "Тут ти зможеш створювати нагадування, отримувати їх у потрібний час, "
        "керувати списками та переглядати статистику.\n\n"
        "Зараз доступно:\n"
        "📋 /help — усі команди та підказки\n\n"
        "<i>Наступні кроки: створення нагадувань, списки, повтори, часовий пояс.</i>"
    )
    await update.effective_message.reply_text(text, parse_mode="HTML")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📖 <b>Довідка</b>\n\n"
        "<b>Вже працює:</b>\n"
        "/start — привітання\n"
        "/help — ця довідка\n\n"
        "<b>Далі з’являться:</b>\n"
        "/add — нове нагадування\n"
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
    app.add_error_handler(error_handler)

    log.info("Бот запущено (polling)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
