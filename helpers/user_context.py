import asyncio

from telegram import Update

from database.users import get_or_create_user


async def ensure_telegram_user(update: Update) -> tuple[int, bool] | None:
    user = update.effective_user
    if not user:
        return None
    return await asyncio.to_thread(get_or_create_user, user.id)
