"""Команда /timezone — перегляд і зміна IANA-часового поясу."""
from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from database.activity import log_activity
from database.users import get_timezone_for_user, set_user_timezone
from helpers.user_context import ensure_telegram_user

log = logging.getLogger(__name__)


async def cmd_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pair = await ensure_telegram_user(update)
    if not pair:
        return
    internal_id, is_new = pair
    if is_new:
        await asyncio.to_thread(log_activity, internal_id, "register", None)

    args = context.args or []
    cur = await asyncio.to_thread(get_timezone_for_user, internal_id)

    if not args:
        await update.effective_message.reply_text(
            f"🌍 Зараз: <code>{cur}</code>\n\n"
            "Щоб змінити: <code>/timezone Europe/Warsaw</code>\n"
            "Список зон: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        await asyncio.to_thread(log_activity, internal_id, "timezone_view", None)
        return

    name = " ".join(args).strip()
    ok = await asyncio.to_thread(set_user_timezone, internal_id, name)
    if not ok:
        await update.effective_message.reply_text(
            "⚠️ Не вдалося встановити пояс. Перевір назву IANA "
            "(наприклад <code>Europe/Kyiv</code>, <code>UTC</code>).",
            parse_mode="HTML",
        )
        return

    await asyncio.to_thread(log_activity, internal_id, "timezone_set", name)
    await update.effective_message.reply_text(
        f"✅ Часовий пояс: <code>{name}</code>\n"
        "Нові нагадування та фрази «нагадай…» враховують його.",
        parse_mode="HTML",
    )
    log.info("timezone user=%s set=%s", internal_id, name)
