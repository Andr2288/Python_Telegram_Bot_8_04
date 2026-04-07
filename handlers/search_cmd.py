from __future__ import annotations

import asyncio
import html
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from database.activity import log_activity
from database.reminders import search_reminders_for_user
from database.users import get_timezone_for_user
from helpers.parsing import safe_zone
from helpers.user_context import ensure_telegram_user

log = logging.getLogger(__name__)

_ST = {
    "active": "🟢 активне",
    "done": "✅ виконано",
    "cancelled": "🚫 скасовано",
}


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pair = await ensure_telegram_user(update)
    if not pair:
        return
    internal_id, is_new = pair
    if is_new:
        await asyncio.to_thread(log_activity, internal_id, "register", None)

    args = context.args or []
    if not args:
        await update.effective_message.reply_text(
            "🔎 <b>Пошук</b>\n\n"
            "<code>/search слово</code> — усі статуси\n"
            "<code>/search кілька слів active</code> — фільтр останнім словом\n"
            "Статуси: <code>active</code>, <code>done</code>, "
            "<code>cancelled</code>, <code>all</code>",
            parse_mode="HTML",
        )
        return

    valid_status = frozenset({"active", "done", "cancelled", "all"})
    if len(args) >= 2 and args[-1].lower() in valid_status:
        status = args[-1].lower()
        keyword = " ".join(args[:-1]).strip()
    else:
        status = None
        keyword = " ".join(args).strip()

    if not keyword:
        await update.effective_message.reply_text("⚠️ Вкажи слово для пошуку.")
        return

    rows = await asyncio.to_thread(
        search_reminders_for_user, internal_id, keyword, status
    )
    await asyncio.to_thread(
        log_activity,
        internal_id,
        "search",
        f"q={keyword!r} status={status!r} n={len(rows)}",
    )

    if not rows:
        await update.effective_message.reply_text(
            f"📭 Нічого не знайдено за «<code>{html.escape(keyword, quote=False)}</code>».",
            parse_mode="HTML",
        )
        return

    tz_name = await asyncio.to_thread(get_timezone_for_user, internal_id)
    tz = safe_zone(tz_name)
    lines = [
        f"🔎 Знайдено: <b>{len(rows)}</b>\n",
    ]
    for r in rows:
        st = _ST.get(str(r["status"]), str(r["status"]))
        dt = datetime.fromisoformat(str(r["remind_at"]).replace("Z", "+00:00"))
        local = dt.astimezone(tz).strftime("%d.%m.%Y %H:%M")
        snippet = html.escape(str(r["text"])[:100], quote=False)
        rep = " 🔁" if r.get("repeat_rule") else ""
        lines.append(
            f"• id <code>{r['id']}</code>{rep} — {st}\n"
            f"  🕐 {local}\n"
            f"  {snippet}"
        )
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3997] + "…"
    await update.effective_message.reply_text(text, parse_mode="HTML")
    log.info("search user=%s n=%s", internal_id, len(rows))
