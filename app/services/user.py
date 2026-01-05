from loguru import logger
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.db.repositories import user as user_repo
from app.bot.core import bot


async def notify_user(message: str, user_id: int | None, group_id: int | None = None):
    try:
        await bot.send_message(chat_id=group_id if group_id is not None else user_id,
                               text=message, parse_mode="HTML")
    except Exception as e:
        logger.error(e)


async def kick_user(group_id: int, user_id: int):
    try:
        await bot.ban_chat_member(group_id, user_id)
        await bot.unban_chat_member(group_id, user_id)
    except Exception as e:
        logger.error(e)


class UserService:
    def __init__(self, session: async_sessionmaker):
        self.session = session

    async def get_or_create_user(self, user_id: int, first_name: str | None = None, last_name: str | None = None,
                                 username: str | None = None, is_bot: bool | None = None, locale: str | None = None):
        async with self.session() as session:
            user = await user_repo.get_or_create_user(session, user_id=user_id, first_name=first_name,
                                                      last_name=last_name, username=username, is_bot=is_bot, user_locale=locale)
        return user

    async def get_group_admins(self, group_id: int):
        async with self.session() as session:
            return await user_repo.get_group_admins(session, group_id)

    async def notify_admins(self, message: str, group_id: int):
        admins = await self.get_group_admins(group_id)
        for admin in admins:
            await notify_user(user_id=admin.id, message=message)
