from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def safe_zone(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name.strip())
    except (ZoneInfoNotFoundError, KeyError, ValueError):
        return ZoneInfo("Europe/Kyiv")


def parse_local_date(text: str, tz: ZoneInfo) -> date | None:
    s = text.strip()
    if not s:
        return None
    today = datetime.now(tz).date()
    low = s.lower()
    if low in ("сьогодні", "сегодня", "today"):
        return today
    if low in ("завтра", "tomorrow"):
        return today + timedelta(days=1)
    if low in ("післязавтра", "послезавтра"):
        return today + timedelta(days=2)
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_hhmm(text: str) -> tuple[int, int] | None:
    m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", text.strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if 0 <= h <= 23 and 0 <= mi <= 59:
        return h, mi
    return None


def local_datetime_to_utc_iso(d: date, hour: int, minute: int, tz: ZoneInfo) -> str:
    local = datetime(d.year, d.month, d.day, hour, minute, tzinfo=tz)
    utc = local.astimezone(ZoneInfo("UTC"))
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")
