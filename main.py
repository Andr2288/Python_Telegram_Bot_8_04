"""Точка входу: Telegram-бот нагадувань (JobQueue + /list)."""
import asyncio
import logging
import sys

from telegram import Update
from telegram.error import Conflict
from telegram.ext import Application, CommandHandler, ContextTypes

from jobs.reminder_jobs import schedule_all_pending_jobs

from config import BOT_TOKEN
from database.activity import log_activity
from database.db import init_db
from handlers.add import build_add_conversation_handler
from handlers.delete_cmd import cmd_delete
from handlers.edit_cmd import build_edit_conversation_handler
from handlers.history_cmd import cmd_history
from handlers.list_cmd import cmd_list
from handlers.natural_cmd import build_natural_message_handler
from handlers.search_cmd import cmd_search
from handlers.stats_cmd import cmd_stats
from handlers.timezone_cmd import cmd_timezone
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
        "📋 /list — активні нагадування\n"
        "📜 /history — виконані та скасовані\n"
        "✏️ /edit — змінити активне\n"
        "🗑 /delete — скасувати активне\n"
        "🌍 /timezone — часовий пояс\n"
        "🔎 /search — пошук у текстах\n"
        "📊 /stats — статистика\n"
        "❓ /help — усі команди\n"
        "💬 або текст: <code>нагадай завтра о 9 …</code>"
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
        "/add — нове нагадування (текст → дата → час), /cancel — вийти з кроків\n"
        "/list — активні нагадування\n"
        "/history — виконані та скасовані\n"
        "/edit — змінити (id → текст / дата / час), /cancel у діалозі\n"
        "/delete &lt;id&gt; — скасувати активне\n"
        "/timezone — переглянути або змінити пояс (IANA)\n"
        "/search — пошук (останній аргумент може бути статус: active, done, …)\n"
        "/stats — статистика та «найактивніші дні»\n\n"
        "<b>Текстом (без /):</b>\n"
        "<code>нагадай завтра о 9 купити молоко</code>\n"
        "<code>нагадай щодня о 8 ранкова зарядка</code>\n"
        "<code>нагадай щопонеділка о 10 звіт</code>"
    )
    await update.effective_message.reply_text(text, parse_mode="HTML")


async def _post_init(application: Application) -> None:
    await schedule_all_pending_jobs(application)


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

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(CommandHandler("timezone", cmd_timezone))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(build_add_conversation_handler())
    app.add_handler(build_edit_conversation_handler())
    app.add_handler(build_natural_message_handler())
    app.add_error_handler(error_handler)

    log.info("Бот запущено (polling)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
