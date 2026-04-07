from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from database.db import get_connection


def get_or_create_user(telegram_id: int) -> tuple[int, bool]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        if row:
            return int(row["id"]), False
        cur = conn.execute(
            "INSERT INTO users (telegram_id) VALUES (?)", (telegram_id,)
        )
        return int(cur.lastrowid), True


def get_internal_user_id(telegram_id: int) -> int | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return int(row["id"]) if row else None


def get_timezone_for_user(internal_id: int) -> str:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT timezone FROM users WHERE id = ?", (internal_id,)
        ).fetchone()
        if not row or not row["timezone"]:
            return "Europe/Kyiv"
        return str(row["timezone"])


def set_user_timezone(internal_id: int, tz_name: str) -> bool:
    name = tz_name.strip()
    if not name:
        return False
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, KeyError, ValueError):
        return False
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE users SET timezone = ? WHERE id = ?",
            (name, internal_id),
        )
        return cur.rowcount > 0
