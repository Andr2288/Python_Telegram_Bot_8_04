from __future__ import annotations

import asyncio
import html
import logging
from datetime import datetime, timezone

import telegram.error as tg_error
from telegram.ext import Application, ContextTypes

from database.activity import log_activity
from database.reminders import (
    fetch_reminder,
    list_active_reminders_in_future,
    mark_reminder_done,
    set_reminder_next_fire,
)
from database.users import get_timezone_for_user
from helpers.parsing import safe_zone
from helpers.repeat import next_fire_utc_iso

log = logging.getLogger(__name__)


async def fire_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data or {}
    rid = data.get("reminder_id")
    chat_id = data.get("chat_id")
    if rid is None or chat_id is None:
        log.warning("fire_reminder: invalid job.data %s", data)
        return

    row = await asyncio.to_thread(fetch_reminder, int(rid))
    if not row or row["status"] != "active":
        return

    text = str(row["text"])
    user_internal_id = int(row["user_id"])
    safe = html.escape(text, quote=False)
    body = f"⏰ <b>Нагадування</b>\n\n{safe}"
    if len(body) > 4000:
        body = body[:3997] + "…"

    try:
        await context.bot.send_message(chat_id=chat_id, text=body, parse_mode="HTML")
    except tg_error.TelegramError as e:
        log.warning("fire_reminder: send failed id=%s: %s", rid, e)
        return

    repeat = row.get("repeat_rule")
    if repeat:
        tz_name = await asyncio.to_thread(get_timezone_for_user, user_internal_id)
        tz = safe_zone(tz_name)
        next_iso = next_fire_utc_iso(str(row["remind_at"]), str(repeat), tz)
        now_utc = datetime.now(timezone.utc)
        next_dt = (
            datetime.fromisoformat(next_iso.replace("Z", "+00:00"))
            if next_iso
            else None
        )
        if next_iso and next_dt and next_dt > now_utc:
            await asyncio.to_thread(set_reminder_next_fire, int(rid), next_iso)
            cancel_reminder_job(context.application, int(rid))
            schedule_reminder_job(
                context.application, int(rid), int(chat_id), next_iso
            )
            await asyncio.to_thread(
                log_activity, user_internal_id, "repeat", f"reminder_id={rid}"
            )
            log.info("reminder repeat id=%s next=%s", rid, next_iso)
        else:
            await asyncio.to_thread(mark_reminder_done, int(rid))
            await asyncio.to_thread(
                log_activity, user_internal_id, "done", f"reminder_id={rid}"
            )
            log.warning("reminder id=%s: repeat stopped (no valid next fire)", rid)
    else:
        await asyncio.to_thread(mark_reminder_done, int(rid))
        await asyncio.to_thread(
            log_activity, user_internal_id, "done", f"reminder_id={rid}"
        )
        log.info("reminder fired id=%s", rid)


def schedule_reminder_job(
    application: Application,
    reminder_id: int,
    chat_id: int,
    remind_at_utc_iso: str,
) -> None:
    jq = application.job_queue
    if jq is None:
        log.error("JobQueue missing; install python-telegram-bot[job-queue].")
        return
    when = datetime.fromisoformat(remind_at_utc_iso.replace("Z", "+00:00"))
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    if when <= datetime.now(timezone.utc):
        return
    jq.run_once(
        fire_reminder,
        when=when,
        data={"reminder_id": reminder_id, "chat_id": chat_id},
        name=f"reminder_{reminder_id}",
    )
    log.info("scheduled reminder id=%s at=%s", reminder_id, when.isoformat())


async def schedule_all_pending_jobs(application: Application) -> None:
    rows = await asyncio.to_thread(list_active_reminders_in_future)
    for row in rows:
        schedule_reminder_job(
            application,
            int(row["id"]),
            int(row["telegram_id"]),
            str(row["remind_at"]),
        )
    log.info("loaded %s pending reminders from db", len(rows))


def cancel_reminder_job(application: Application, reminder_id: int) -> None:
    jq = application.job_queue
    if jq is None:
        return
    name = f"reminder_{reminder_id}"
    for job in jq.get_jobs_by_name(name):
        job.schedule_removal()
        log.info("removed job %s", name)
