from database.db import get_connection


def log_activity(user_id: int, action: str, details: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO activity_log (user_id, action, details) VALUES (?, ?, ?)",
            (user_id, action, details),
        )
