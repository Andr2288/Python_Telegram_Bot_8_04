"""Команда /history — виконані та скасовані нагадування."""
from __future__ import annotations

import asyncio
import html
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from database.activity import log_activity
from database.reminders import list_history_for_user
from database.users import get_timezone_for_user
from helpers.parsing import safe_zone
from helpers.user_context import ensure_telegram_user

log = logging.getLogger(__name__)

_STATUS_LABEL = {
    "done": "✅ виконано",
    "cancelled": "🚫 скасовано",
}


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pair = await ensure_telegram_user(update)
    if not pair:
        return
    internal_id, is_new = pair
    if is_new:
        await asyncio.to_thread(log_activity, internal_id, "register", None)

    rows = await asyncio.to_thread(list_history_for_user, internal_id)
    await asyncio.to_thread(log_activity, internal_id, "history", None)

    if not rows:
        await update.effective_message.reply_text(
            "📜 Поки порожньо: немає виконаних чи скасованих нагадувань."
        )
        return

    tz_name = await asyncio.to_thread(get_timezone_for_user, internal_id)
    tz = safe_zone(tz_name)
    lines = ["📜 <b>Історія</b> (останні записи)\n"]
    for r in rows:
        st = str(r["status"])
        label = _STATUS_LABEL.get(st, st)
        dt = datetime.fromisoformat(str(r["remind_at"]).replace("Z", "+00:00"))
        local = dt.astimezone(tz).strftime("%d.%m.%Y %H:%M")
        snippet = html.escape(str(r["text"])[:100], quote=False)
        lines.append(
            f"• id <code>{r['id']}</code> — {label}\n"
            f"  🕐 було на: <b>{local}</b>\n"
            f"  {snippet}"
        )
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3997] + "…"
    await update.effective_message.reply_text(text, parse_mode="HTML")
    log.info("history user=%s count=%s", internal_id, len(rows))
