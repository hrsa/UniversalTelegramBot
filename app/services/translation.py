import i18n
from loguru import logger

from app.db.session import async_session_maker
from app.db.repositories import user as user_repo
from app.db.repositories import group as group_repo


async def t_for(
        key: str,
        user_id: int | None = None,
        group_id: int | None = None,
        default_locale: str = "en",
        **kwargs
) -> str:
    async with async_session_maker() as session:
        if user_id is not None:
            locale = await user_repo.get_locale(session, user_id)
        elif group_id is not None:
            locale = await group_repo.get_locale(session, group_id)
        else:
            locale = default_locale
    return i18n.t(key, locale=locale, **kwargs)