from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from database.activity import log_activity
from database.reminders import get_user_reminder_stats
from helpers.user_context import ensure_telegram_user

log = logging.getLogger(__name__)


def _fmt_date(iso_d: str) -> str:
    parts = iso_d.split("-")
    if len(parts) == 3:
        return f"{parts[2]}.{parts[1]}.{parts[0]}"
    return iso_d


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pair = await ensure_telegram_user(update)
    if not pair:
        return
    internal_id, is_new = pair
    if is_new:
        await asyncio.to_thread(log_activity, internal_id, "register", None)

    s = await asyncio.to_thread(get_user_reminder_stats, internal_id)
    await asyncio.to_thread(log_activity, internal_id, "stats", None)

    total = s["total"]
    bs = s["by_status"]
    active = bs.get("active", 0)
    done = bs.get("done", 0)
    cancelled = bs.get("cancelled", 0)

    if total == 0:
        await update.effective_message.reply_text(
            "📊 Поки немає нагадувань у базі. Створи через /add або текстом «нагадай …»."
        )
        return

    pct_done = round(100.0 * done / total, 1) if total else 0.0

    lines = [
        "📊 <b>Статистика</b>\n",
        f"📝 Усього створено записів: <b>{total}</b>",
        f"🟢 Активні: <b>{active}</b>",
        f"✅ Виконані: <b>{done}</b>",
        f"🚫 Скасовані: <b>{cancelled}</b>",
        f"📈 Виконано від загальної кількості: <b>{pct_done}%</b>\n",
        "<b>Найактивніші дні</b> (за кількістю <i>створених</i> нагадувань):",
    ]
    top_c = s["top_days_created"]
    if top_c:
        for d, c in top_c:
            lines.append(f"• {_fmt_date(d)} — <b>{c}</b> шт.")
    else:
        lines.append("• —")

    lines.append("\n<b>Найбільше спрацювань</b> (день завершення <code>done</code>):")
    top_d = s["top_days_done"]
    if top_d:
        for d, c in top_d:
            lines.append(f"• {_fmt_date(d)} — <b>{c}</b> шт.")
    else:
        lines.append("• —")

    text = "\n".join(lines)
    await update.effective_message.reply_text(text, parse_mode="HTML")
    log.info("stats user=%s total=%s", internal_id, total)
