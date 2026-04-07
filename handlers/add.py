"""Структуроване створення нагадування: /add → текст → дата → час."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from database.activity import log_activity
from database.reminders import insert_reminder
from database.users import get_timezone_for_user
from helpers.parsing import (
    local_datetime_to_utc_iso,
    parse_hhmm,
    parse_local_date,
    safe_zone,
)
from helpers.user_context import ensure_telegram_user

log = logging.getLogger(__name__)

STATE_TEXT, STATE_DATE, STATE_TIME = range(3)


async def add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    for key in ("add_text", "add_date", "add_internal_id"):
        context.user_data.pop(key, None)
    await update.message.reply_text("🚫 Створення нагадування скасовано.")
    return ConversationHandler.END


async def add_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pair = await ensure_telegram_user(update)
    if not pair:
        return ConversationHandler.END
    internal_id, is_new = pair
    if is_new:
        await asyncio.to_thread(log_activity, internal_id, "register", None)
    context.user_data["add_internal_id"] = internal_id
    await update.message.reply_text(
        "➕ <b>Нове нагадування</b>\n\n"
        "Крок 1/3: напиши текст, про що нагадати.\n"
        "Скасувати: /cancel",
        parse_mode="HTML",
    )
    return STATE_TEXT


async def add_receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if len(text) < 1:
        await update.message.reply_text(
            "⚠️ Текст занадто короткий. Спробуй ще раз або /cancel."
        )
        return STATE_TEXT
    if len(text) > 500:
        await update.message.reply_text(
            "⚠️ До 500 символів. Скороти текст або /cancel."
        )
        return STATE_TEXT
    context.user_data["add_text"] = text
    await update.message.reply_text(
        "Крок 2/3: дата\n"
        "Приклади: <code>25.12.2026</code>, <code>2026-12-25</code>, "
        "<code>завтра</code>, <code>сьогодні</code>",
        parse_mode="HTML",
    )
    return STATE_DATE


async def add_receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    internal_id = context.user_data.get("add_internal_id")
    if not internal_id:
        await update.message.reply_text("Почни з /add")
        return ConversationHandler.END
    tz_name = await asyncio.to_thread(get_timezone_for_user, internal_id)
    tz = safe_zone(tz_name)
    d = parse_local_date(update.message.text or "", tz)
    if not d:
        await update.message.reply_text(
            "⚠️ Не зрозумів дату. Спробуй <code>ДД.ММ.РРРР</code>, "
            "<code>РРРР-ММ-ДД</code> або <code>сьогодні</code> / <code>завтра</code>. /cancel",
            parse_mode="HTML",
        )
        return STATE_DATE
    context.user_data["add_date"] = d.isoformat()
    await update.message.reply_text(
        "Крок 3/3: час у твоєму часовому поясі\n"
        "Формат <code>ГГ:ХХ</code> (24 год), наприклад <code>09:00</code> або <code>14:30</code>",
        parse_mode="HTML",
    )
    return STATE_TIME


async def add_receive_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    internal_id = context.user_data.get("add_internal_id")
    text_rem = context.user_data.get("add_text")
    date_iso = context.user_data.get("add_date")
    if not all([internal_id, text_rem, date_iso]):
        await update.message.reply_text("Почни з /add")
        return ConversationHandler.END

    hm = parse_hhmm(update.message.text or "")
    if not hm:
        await update.message.reply_text(
            "⚠️ Формат часу <code>ГГ:ХХ</code>, наприклад <code>9:15</code>. /cancel",
            parse_mode="HTML",
        )
        return STATE_TIME

    d = date.fromisoformat(date_iso)
    h, m = hm
    tz_name = await asyncio.to_thread(get_timezone_for_user, internal_id)
    tz = safe_zone(tz_name)
    utc_iso = local_datetime_to_utc_iso(d, h, m, tz)

    dt_utc = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    if dt_utc <= datetime.now(timezone.utc):
        await update.message.reply_text(
            "⚠️ Цей момент уже минув. Обери іншу дату або час (у твоєму поясі). /cancel",
            parse_mode="HTML",
        )
        return STATE_TIME

    rid = await asyncio.to_thread(insert_reminder, internal_id, text_rem, utc_iso)
    await asyncio.to_thread(log_activity, internal_id, "create", f"reminder_id={rid}")
    log.info("reminder created id=%s user=%s at_utc=%s", rid, internal_id, utc_iso)

    local_show = dt_utc.astimezone(tz).strftime("%d.%m.%Y %H:%M")
    for key in ("add_text", "add_date", "add_internal_id"):
        context.user_data.pop(key, None)

    await update.message.reply_text(
        f"✅ Нагадування збережено (id <code>{rid}</code>).\n"
        f"🕐 Заплановано (твій пояс <code>{tz_name}</code>): <b>{local_show}</b>\n\n"
        "<i>Надсилання в чат у цей час — на наступному кроці (планувальник).</i>",
        parse_mode="HTML",
    )
    return ConversationHandler.END


def build_add_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("add", add_entry)],
        states={
            STATE_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_receive_text)
            ],
            STATE_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_receive_date)
            ],
            STATE_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_receive_time)
            ],
        },
        fallbacks=[CommandHandler("cancel", add_cancel)],
        name="add_reminder",
        allow_reentry=True,
    )
