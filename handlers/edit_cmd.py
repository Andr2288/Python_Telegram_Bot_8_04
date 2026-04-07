"""Діалог /edit — зміна тексту, дати та часу активного нагадування."""
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
from database.reminders import fetch_reminder, update_reminder_active
from database.users import get_timezone_for_user
from helpers.parsing import (
    local_datetime_to_utc_iso,
    parse_hhmm,
    parse_local_date,
    safe_zone,
)
from helpers.user_context import ensure_telegram_user
from jobs.reminder_jobs import cancel_reminder_job, schedule_reminder_job

log = logging.getLogger(__name__)

E_ID, E_TEXT, E_DATE, E_TIME = range(4)

_EDIT_KEYS = (
    "edit_internal_id",
    "edit_rid",
    "edit_text",
    "edit_date",
)


def _clear_edit_data(context: ContextTypes.DEFAULT_TYPE) -> None:
    for k in _EDIT_KEYS:
        context.user_data.pop(k, None)


async def edit_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear_edit_data(context)
    await update.message.reply_text("🚫 Редагування скасовано.")
    return ConversationHandler.END


async def edit_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    pair = await ensure_telegram_user(update)
    if not pair:
        return ConversationHandler.END
    internal_id, is_new = pair
    if is_new:
        await asyncio.to_thread(log_activity, internal_id, "register", None)
    context.user_data["edit_internal_id"] = internal_id
    await update.message.reply_text(
        "✏️ <b>Редагування</b>\n\n"
        "Введи <b>id</b> активного нагадування з /list.\n"
        "Скасувати: /cancel",
        parse_mode="HTML",
    )
    return E_ID


async def edit_receive_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    internal_id = context.user_data.get("edit_internal_id")
    if internal_id is None:
        return ConversationHandler.END
    raw = (update.message.text or "").strip()
    try:
        rid = int(raw)
    except ValueError:
        await update.message.reply_text("⚠️ Потрібне число (id). Спробуй ще або /cancel")
        return E_ID

    row = await asyncio.to_thread(fetch_reminder, rid)
    if not row or int(row["user_id"]) != int(internal_id):
        await update.message.reply_text("⚠️ Не знайдено або не твоє. Інший id або /cancel")
        return E_ID
    if str(row["status"]) != "active":
        await update.message.reply_text("⚠️ Можна редагувати лише активні нагадування. /cancel")
        return E_ID

    context.user_data["edit_rid"] = rid
    await update.message.reply_text(
        "Новий <b>текст</b> нагадування.\n"
        "Напиши <code>-</code> або <code>без змін</code>, щоб залишити як є.",
        parse_mode="HTML",
    )
    return E_TEXT


async def edit_receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    rid = context.user_data.get("edit_rid")
    internal_id = context.user_data.get("edit_internal_id")
    if rid is None or internal_id is None:
        await update.message.reply_text("Почни з /edit")
        return ConversationHandler.END

    t = (update.message.text or "").strip()
    if t in ("-", "—", "без змін", "без змін.", "skip"):
        row = await asyncio.to_thread(fetch_reminder, int(rid))
        text = str(row["text"]) if row else ""
    else:
        text = t
    if len(text) < 1:
        await update.message.reply_text("⚠️ Текст порожній. Спробуй ще або /cancel")
        return E_TEXT
    if len(text) > 500:
        await update.message.reply_text("⚠️ До 500 символів. /cancel")
        return E_TEXT

    context.user_data["edit_text"] = text
    await update.message.reply_text(
        "Нова <b>дата</b> (твій часовий пояс).\n"
        "Приклади: <code>25.12.2026</code>, <code>завтра</code>, <code>сьогодні</code>",
        parse_mode="HTML",
    )
    return E_DATE


async def edit_receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    internal_id = context.user_data.get("edit_internal_id")
    rid = context.user_data.get("edit_rid")
    if internal_id is None or rid is None:
        await update.message.reply_text("Почни з /edit")
        return ConversationHandler.END

    tz_name = await asyncio.to_thread(get_timezone_for_user, int(internal_id))
    tz = safe_zone(tz_name)
    d = parse_local_date(update.message.text or "", tz)
    if not d:
        await update.message.reply_text(
            "⚠️ Не зрозумів дату. Спробуй ДД.ММ.РРРР або «завтра». /cancel",
            parse_mode="HTML",
        )
        return E_DATE
    context.user_data["edit_date"] = d.isoformat()
    await update.message.reply_text(
        "Новий <b>час</b> <code>ГГ:ХХ</code> (24 год), наприклад <code>15:30</code>",
        parse_mode="HTML",
    )
    return E_TIME


async def edit_receive_time(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    internal_id = context.user_data.get("edit_internal_id")
    rid = context.user_data.get("edit_rid")
    text_rem = context.user_data.get("edit_text")
    date_iso = context.user_data.get("edit_date")
    if None in (internal_id, rid, text_rem, date_iso):
        await update.message.reply_text("Почни з /edit")
        return ConversationHandler.END

    hm = parse_hhmm(update.message.text or "")
    if not hm:
        await update.message.reply_text("⚠️ Формат <code>ГГ:ХХ</code>. /cancel", parse_mode="HTML")
        return E_TIME

    d = date.fromisoformat(str(date_iso))
    h, m = hm
    tz_name = await asyncio.to_thread(get_timezone_for_user, int(internal_id))
    tz = safe_zone(tz_name)
    utc_iso = local_datetime_to_utc_iso(d, h, m, tz)

    dt_utc = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    if dt_utc <= datetime.now(timezone.utc):
        await update.message.reply_text(
            "⚠️ Обери час у майбутньому. Інша дата/час або /cancel",
            parse_mode="HTML",
        )
        return E_TIME

    cancel_reminder_job(context.application, int(rid))
    ok = await asyncio.to_thread(
        update_reminder_active, int(rid), int(internal_id), text_rem, utc_iso
    )
    if not ok:
        await update.message.reply_text("⚠️ Не вдалося оновити (можливо, вже не активне). /edit")
        _clear_edit_data(context)
        return ConversationHandler.END

    chat_id = update.effective_user.id
    schedule_reminder_job(context.application, int(rid), chat_id, utc_iso)
    await asyncio.to_thread(
        log_activity, int(internal_id), "edit", f"reminder_id={rid}"
    )
    log.info("reminder edited id=%s user=%s at=%s", rid, internal_id, utc_iso)

    local_show = dt_utc.astimezone(tz).strftime("%d.%m.%Y %H:%M")
    _clear_edit_data(context)
    await update.message.reply_text(
        f"✅ Нагадування <code>{rid}</code> оновлено.\n"
        f"🕐 Новий час (<code>{tz_name}</code>): <b>{local_show}</b>\n"
        "🔔 Надішлю в чат у цей момент.",
        parse_mode="HTML",
    )
    return ConversationHandler.END


def build_edit_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("edit", edit_entry)],
        states={
            E_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_receive_id)],
            E_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_receive_text)],
            E_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_receive_date)],
            E_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_receive_time)],
        },
        fallbacks=[CommandHandler("cancel", edit_cancel)],
        name="edit_reminder",
        allow_reentry=True,
    )
