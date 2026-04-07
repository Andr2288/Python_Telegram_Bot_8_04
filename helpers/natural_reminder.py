"""Розбір фраз на кшталт «нагадай завтра о 9 купити молоко»."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from helpers.parsing import local_datetime_to_utc_iso
from helpers.repeat import next_weekday_date

_NAGADAY = re.compile(r"^\s*нагадай\s+", re.IGNORECASE | re.UNICODE)

_REPEAT_PREFIXES: list[tuple[str, str]] = [
    (r"щопонеділка\s+", "weekly:0"),
    (r"щовівторка\s+", "weekly:1"),
    (r"щосереди\s+", "weekly:2"),
    (r"щочетверга\s+", "weekly:3"),
    (r"щоп['’]ятниці\s+", "weekly:4"),
    (r"щосуботи\s+", "weekly:5"),
    (r"щонеділі\s+", "weekly:6"),
    (r"кожен\s+день\s+", "daily"),
    (r"щодня\s+", "daily"),
    (r"кожного\s+тижня\s+", "weekly"),
    (r"щотижня\s+", "weekly"),
    (r"кожного\s+місяця\s+", "monthly"),
    (r"щомісяця\s+", "monthly"),
]

_TIME_RE = re.compile(
    r"(?i)(?:о|в|у)\s*(\d{1,2})(?::(\d{2}))?(?!\d)"
)


@dataclass
class NaturalParseResult:
    is_nagaday: bool
    ok: bool
    text: str = ""
    utc_iso: str | None = None
    repeat_rule: str | None = None
    clarify: str | None = None


def _extract_date(rest: str, tz: ZoneInfo) -> tuple[date | None, str]:
    low = rest.lower()
    today = datetime.now(tz).date()
    phrases = [
        ("післязавтра", 2),
        ("завтра", 1),
        ("сьогодні", 0),
        ("сегодня", 0),
    ]
    for phrase, delta in phrases:
        idx = low.find(phrase)
        if idx >= 0:
            d = today + timedelta(days=delta)
            new_rest = (rest[:idx] + " " + rest[idx + len(phrase) :]).strip()
            new_rest = re.sub(r"\s+", " ", new_rest)
            return d, new_rest
    m = re.search(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b", rest)
    if not m:
        return None, rest
    dd, mm, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        d = date(yy, mm, dd)
    except ValueError:
        return None, rest
    new_rest = (rest[: m.start()] + " " + rest[m.end() :]).strip()
    new_rest = re.sub(r"\s+", " ", new_rest)
    return d, new_rest


def parse_natural_reminder(raw: str, tz: ZoneInfo) -> NaturalParseResult:
    if not raw or not _NAGADAY.match(raw):
        return NaturalParseResult(is_nagaday=False, ok=False)

    m0 = _NAGADAY.match(raw)
    assert m0 is not None
    rest = raw[m0.end() :].strip()
    if not rest:
        return NaturalParseResult(
            is_nagaday=True,
            ok=False,
            clarify="Напиши, коли і про що нагадати. Приклад: "
            "<code>нагадай завтра о 9 купити молоко</code>",
        )

    repeat_rule: str | None = None
    for pattern, rule in _REPEAT_PREFIXES:
        m = re.match(pattern, rest, re.IGNORECASE)
        if m:
            repeat_rule = rule
            rest = rest[m.end() :].strip()
            break

    tm = _TIME_RE.search(rest)
    if not tm:
        return NaturalParseResult(
            is_nagaday=True,
            ok=False,
            clarify="Додай час: <code>о 9</code> або <code>о 14:30</code>. "
            "Приклад: <code>нагадай завтра о 9 текст</code>",
        )
    hour = int(tm.group(1))
    minute = int(tm.group(2)) if tm.group(2) else 0
    if hour > 23 or minute > 59:
        return NaturalParseResult(
            is_nagaday=True,
            ok=False,
            clarify="⚠️ Година 0–23, хвилини 0–59.",
        )

    rest = (rest[: tm.start()] + " " + rest[tm.end() :]).strip()
    rest = re.sub(r"\s+", " ", rest)

    d: date | None = None
    if repeat_rule and repeat_rule.startswith("weekly:"):
        wd = int(repeat_rule.split(":", 1)[1])
        d = next_weekday_date(tz, wd, hour, minute)
    else:
        d, rest = _extract_date(rest, tz)
        if d is None and repeat_rule == "daily":
            today = datetime.now(tz).date()
            cand = datetime(today.year, today.month, today.day, hour, minute, tzinfo=tz)
            if cand > datetime.now(tz):
                d = today
            else:
                d = today + timedelta(days=1)
        if d is None and repeat_rule == "weekly":
            return NaturalParseResult(
                is_nagaday=True,
                ok=False,
                clarify="Для «щотижня» вкажи перший день: "
                "<code>нагадай щотижня завтра о 10 нарада</code>",
            )
        if d is None and repeat_rule == "monthly":
            return NaturalParseResult(
                is_nagaday=True,
                ok=False,
                clarify="Для «щомісяця» вкажи дату першого разу, наприклад "
                "<code>15.04.2026</code> або <code>завтра</code>.",
            )

    if d is None:
        return NaturalParseResult(
            is_nagaday=True,
            ok=False,
            clarify="Вкажи дату: <code>завтра</code>, <code>сьогодні</code> "
            "або <code>ДД.ММ.РРРР</code>.",
        )

    task = rest.strip()
    if len(task) < 1:
        return NaturalParseResult(
            is_nagaday=True,
            ok=False,
            clarify="Додай короткий текст нагадування (про що саме).",
        )
    if len(task) > 500:
        return NaturalParseResult(
            is_nagaday=True,
            ok=False,
            clarify="⚠️ До 500 символів у тексті.",
        )

    utc_iso = local_datetime_to_utc_iso(d, hour, minute, tz)
    dt_utc = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    if dt_utc <= datetime.now(timezone.utc):
        return NaturalParseResult(
            is_nagaday=True,
            ok=False,
            clarify="⚠️ Цей момент уже минув. Обери пізніший час або дату.",
        )

    return NaturalParseResult(
        is_nagaday=True,
        ok=True,
        text=task,
        utc_iso=utc_iso,
        repeat_rule=repeat_rule,
    )
