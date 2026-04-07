"""Повідомлення, що починаються з «нагадай …»."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes, MessageHandler, filters

from database.activity import log_activity
from database.reminders import insert_reminder
from database.users import get_timezone_for_user
from helpers.natural_reminder import parse_natural_reminder
from helpers.parsing import safe_zone
from helpers.user_context import ensure_telegram_user
from jobs.reminder_jobs import schedule_reminder_job

log = logging.getLogger(__name__)

_QUICK_NAGADAY = re.compile(r"^\s*нагадай\s+", re.IGNORECASE | re.UNICODE)


def _repeat_hint(rule: str | None) -> str:
    if not rule:
        return ""
    low = rule.lower()
    if low == "daily":
        return "\n🔁 Повтор: <b>щодня</b>"
    if low == "weekly" or low.startswith("weekly:"):
        return "\n🔁 Повтор: <b>щотижня</b>"
    if low == "monthly":
        return "\n🔁 Повтор: <b>щомісяця</b>"
    return ""


async def handle_natural_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        return
    text = update.message.text if update.message else ""
    if not text or not _QUICK_NAGADAY.match(text):
        return

    pair = await ensure_telegram_user(update)
    if not pair:
        return
    internal_id, is_new = pair
    if is_new:
        await asyncio.to_thread(log_activity, internal_id, "register", None)

    tz_name = await asyncio.to_thread(get_timezone_for_user, internal_id)
    tz = safe_zone(tz_name)
    result = parse_natural_reminder(text, tz)

    if not result.is_nagaday:
        return
    if not result.ok:
        if result.clarify:
            await update.effective_message.reply_text(
                result.clarify, parse_mode="HTML"
            )
        return

    rid = await asyncio.to_thread(
        insert_reminder,
        internal_id,
        result.text,
        result.utc_iso,
        result.repeat_rule,
    )
    await asyncio.to_thread(
        log_activity, internal_id, "create", f"reminder_id={rid} natural"
    )
    chat_id = update.effective_user.id
    schedule_reminder_job(context.application, rid, chat_id, result.utc_iso)

    dt_utc = datetime.fromisoformat(result.utc_iso.replace("Z", "+00:00"))
    local_show = dt_utc.astimezone(tz).strftime("%d.%m.%Y %H:%M")
    hint = _repeat_hint(result.repeat_rule)
    await update.effective_message.reply_text(
        f"✅ Записано (id <code>{rid}</code>).\n"
        f"🕐 <b>{local_show}</b> ({tz_name}){hint}\n"
        "🔔 Нагадування прийде в цей час.",
        parse_mode="HTML",
    )
    log.info("natural reminder id=%s user=%s", rid, internal_id)


def build_natural_message_handler() -> MessageHandler:
    return MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_natural_reminder,
    )
