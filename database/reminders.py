from database.db import get_connection


def insert_reminder(user_id: int, text: str, remind_at_utc_iso: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO reminders (user_id, text, remind_at, status)
            VALUES (?, ?, ?, 'active')
            """,
            (user_id, text.strip(), remind_at_utc_iso),
        )
        return int(cur.lastrowid)
