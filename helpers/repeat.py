from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from helpers.parsing import local_datetime_to_utc_iso


def add_one_month(d: date) -> date:
    y, m, day = d.year, d.month, d.day
    if m == 12:
        y, m = y + 1, 1
    else:
        m += 1
    last = monthrange(y, m)[1]
    return date(y, m, min(day, last))


def next_weekday_date(
    tz: ZoneInfo, target_weekday: int, hour: int, minute: int
) -> date:
    now = datetime.now(tz)
    today_d = now.date()
    for add in range(0, 370):
        cand = today_d + timedelta(days=add)
        if cand.weekday() != target_weekday:
            continue
        cand_dt = datetime(cand.year, cand.month, cand.day, hour, minute, tzinfo=tz)
        if cand_dt > now:
            return cand
    return today_d + timedelta(days=7)


def next_fire_utc_iso(current_utc_iso: str, repeat_rule: str, tz: ZoneInfo) -> str | None:
    rule = (repeat_rule or "").strip().lower()
    if not rule:
        return None
    dt_utc = datetime.fromisoformat(current_utc_iso.replace("Z", "+00:00"))
    local = dt_utc.astimezone(tz)
    d0, h, mi = local.date(), local.hour, local.minute

    if rule == "daily":
        nd = d0 + timedelta(days=1)
    elif rule == "weekly" or rule.startswith("weekly:"):
        nd = d0 + timedelta(days=7)
    elif rule == "monthly":
        nd = add_one_month(d0)
    else:
        return None
    return local_datetime_to_utc_iso(nd, h, mi, tz)
