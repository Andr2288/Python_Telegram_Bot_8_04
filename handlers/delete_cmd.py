from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from database.activity import log_activity
from database.reminders import cancel_reminder_for_user, fetch_reminder
from helpers.user_context import ensure_telegram_user
from jobs.reminder_jobs import cancel_reminder_job

log = logging.getLogger(__name__)


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pair = await ensure_telegram_user(update)
    if not pair:
        return
    internal_id, is_new = pair
    if is_new:
        await asyncio.to_thread(log_activity, internal_id, "register", None)

    args = context.args or []
    if len(args) != 1:
        await update.effective_message.reply_text(
            "Формат: <code>/delete 5</code>\n"
            "(число — id з повідомлення /list)\n\n"
            "Нагадування буде <b>скасовано</b> (залишиться в історії).",
            parse_mode="HTML",
        )
        return

    try:
        rid = int(args[0].strip())
    except ValueError:
        await update.effective_message.reply_text("⚠️ id має бути числом, наприклад /delete 3")
        return

    row = await asyncio.to_thread(fetch_reminder, rid)
    if not row or int(row["user_id"]) != internal_id:
        await update.effective_message.reply_text(
            "⚠️ Нагадування не знайдено або воно не твоє."
        )
        return
    if str(row["status"]) != "active":
        await update.effective_message.reply_text(
            "⚠️ Це нагадування вже не активне (див. /history)."
        )
        return

    ok = await asyncio.to_thread(cancel_reminder_for_user, rid, internal_id)
    if not ok:
        await update.effective_message.reply_text("⚠️ Не вдалося скасувати. Спробуй ще раз.")
        return

    cancel_reminder_job(context.application, rid)
    await asyncio.to_thread(log_activity, internal_id, "cancel", f"reminder_id={rid}")

    await update.effective_message.reply_text(
        f"🚫 Нагадування <code>{rid}</code> скасовано.\n"
        "Воно з’явиться в /history як «скасовано».",
        parse_mode="HTML",
    )
    log.info("delete/cancel reminder id=%s user=%s", rid, internal_id)
