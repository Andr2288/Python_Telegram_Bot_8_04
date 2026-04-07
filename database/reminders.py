from __future__ import annotations

from datetime import datetime, timezone

from database.db import get_connection


def insert_reminder(
    user_id: int,
    text: str,
    remind_at_utc_iso: str,
    repeat_rule: str | None = None,
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO reminders (user_id, text, remind_at, status, repeat_rule)
            VALUES (?, ?, ?, 'active', ?)
            """,
            (user_id, text.strip(), remind_at_utc_iso, repeat_rule),
        )
        return int(cur.lastrowid)


def set_reminder_next_fire(reminder_id: int, remind_at_utc_iso: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE reminders
            SET remind_at = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (remind_at_utc_iso, reminder_id),
        )


def fetch_reminder(reminder_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, text, remind_at, status, repeat_rule
            FROM reminders WHERE id = ?
            """,
            (reminder_id,),
        ).fetchone()
        return dict(row) if row else None


def mark_reminder_done(reminder_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE reminders
            SET status = 'done', updated_at = datetime('now')
            WHERE id = ?
            """,
            (reminder_id,),
        )


def list_active_reminders_in_future() -> list[dict]:
    """Активні нагадування з remind_at у майбутньому; поля id, remind_at, telegram_id."""
    now = datetime.now(timezone.utc)
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT r.id, r.remind_at, u.telegram_id
            FROM reminders r
            JOIN users u ON u.id = r.user_id
            WHERE r.status = 'active'
            ORDER BY r.remind_at
            """
        ).fetchall()
    out: list[dict] = []
    for row in rows:
        d = dict(row)
        dt = datetime.fromisoformat(str(d["remind_at"]).replace("Z", "+00:00"))
        if dt > now:
            out.append(d)
    return out


def list_active_reminders_for_user(internal_user_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, text, remind_at, repeat_rule
            FROM reminders
            WHERE user_id = ? AND status = 'active'
            ORDER BY remind_at
            """,
            (internal_user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def cancel_reminder_for_user(reminder_id: int, internal_user_id: int) -> bool:
    """Статус cancelled, лише якщо нагадування активне і належить користувачу."""
    with get_connection() as conn:
        cur = conn.execute(
            """
            UPDATE reminders
            SET status = 'cancelled', updated_at = datetime('now')
            WHERE id = ? AND user_id = ? AND status = 'active'
            """,
            (reminder_id, internal_user_id),
        )
        return cur.rowcount > 0


def update_reminder_active(
    reminder_id: int,
    internal_user_id: int,
    text: str,
    remind_at_utc_iso: str,
) -> bool:
    with get_connection() as conn:
        cur = conn.execute(
            """
            UPDATE reminders
            SET text = ?, remind_at = ?, updated_at = datetime('now')
            WHERE id = ? AND user_id = ? AND status = 'active'
            """,
            (text.strip(), remind_at_utc_iso, reminder_id, internal_user_id),
        )
        return cur.rowcount > 0


def list_history_for_user(internal_user_id: int, limit: int = 40) -> list[dict]:
    """Виконані та скасовані, новіші зверху."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, text, remind_at, status, updated_at
            FROM reminders
            WHERE user_id = ? AND status IN ('done', 'cancelled')
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (internal_user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def search_reminders_for_user(
    internal_user_id: int,
    keyword: str,
    status: str | None = None,
    limit: int = 25,
) -> list[dict]:
    """
    Підрядок у тексті (без урахування регістру).
    status: None або 'all' — усі; інакше 'active' | 'done' | 'cancelled'.
    """
    kw = keyword.strip().lower()
    if not kw:
        return []
    st = (status or "").strip().lower()
    if st in ("", "all"):
        sql = """
            SELECT id, text, remind_at, status, repeat_rule
            FROM reminders
            WHERE user_id = ? AND instr(lower(text), ?) > 0
            ORDER BY created_at DESC
            LIMIT ?
        """
        params: tuple = (internal_user_id, kw, limit)
    elif st in ("active", "done", "cancelled"):
        sql = """
            SELECT id, text, remind_at, status, repeat_rule
            FROM reminders
            WHERE user_id = ? AND status = ? AND instr(lower(text), ?) > 0
            ORDER BY created_at DESC
            LIMIT ?
        """
        params = (internal_user_id, st, kw, limit)
    else:
        return []

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def get_user_reminder_stats(internal_user_id: int) -> dict:
    """Агрегати для /stats і топ днів за кількістю створених нагадувань."""
    with get_connection() as conn:
        total = int(
            conn.execute(
                "SELECT COUNT(*) FROM reminders WHERE user_id = ?",
                (internal_user_id,),
            ).fetchone()[0]
        )
        by_status: dict[str, int] = {}
        for row in conn.execute(
            """
            SELECT status, COUNT(*) FROM reminders
            WHERE user_id = ? GROUP BY status
            """,
            (internal_user_id,),
        ).fetchall():
            by_status[str(row[0])] = int(row[1])

        top_created = conn.execute(
            """
            SELECT date(created_at) AS d, COUNT(*) AS c
            FROM reminders
            WHERE user_id = ?
            GROUP BY date(created_at)
            ORDER BY c DESC, d DESC
            LIMIT 5
            """,
            (internal_user_id,),
        ).fetchall()

        top_done = conn.execute(
            """
            SELECT date(updated_at) AS d, COUNT(*) AS c
            FROM reminders
            WHERE user_id = ? AND status = 'done'
            GROUP BY date(updated_at)
            ORDER BY c DESC, d DESC
            LIMIT 5
            """,
            (internal_user_id,),
        ).fetchall()

    return {
        "total": total,
        "by_status": by_status,
        "top_days_created": [(str(r[0]), int(r[1])) for r in top_created],
        "top_days_done": [(str(r[0]), int(r[1])) for r in top_done],
    }
