"""Користувачі Telegram ↔ внутрішній id у SQLite."""
from database.db import get_connection


def get_or_create_user(telegram_id: int) -> tuple[int, bool]:
    """
    Повертає (internal_user_id, created_new).
    internal_user_id — первинний ключ таблиці users.
    """
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
