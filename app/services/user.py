from sqlalchemy.ext.asyncio import async_sessionmaker
from app.db.repositories import user as user_repo


class UserService:
    def __init__(self, session: async_sessionmaker):
        self.session = session

    async def get_or_create_user(self, user_id: int, first_name: str | None = None, last_name: str | None = None,
                                 username: str | None = None, is_bot: bool = False):
        async with self.session() as session:
            user = await user_repo.get_or_create_user(session, user_id=user_id, first_name=first_name,
                                                      last_name=last_name, username=username, is_bot=is_bot)
        return user

    async def get_group_admins(self, group_id: int):
        async with self.session() as session:
            return await user_repo.get_group_admins(session, group_id)
