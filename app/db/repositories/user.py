import locale

from sqlalchemy import Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.models.group_member import GroupMember
from app.db.models.user import User


async def get_or_create_user(
        session: AsyncSession,
        user_id: int,
        first_name: str | None = None,
        last_name: str | None = None,
        username: str | None = None,
        user_locale: str | None = None,
        is_bot: bool | None = None,
) -> User:
    user = await get_user(session=session, user_id=user_id)
    if user is None:
        user = await create_user(session=session, user_id=user_id, first_name=first_name, last_name=last_name,
                                 username=username, user_locale=user_locale, is_bot=is_bot)
    return user


async def create_user(session: AsyncSession, user_id: int, first_name: str | None = None, last_name: str | None = None,
                      username: str | None = None, user_locale: str | None = None, is_bot: bool = False) -> User:
    user = User(id=user_id, first_name=first_name, last_name=last_name, username=username,
                locale=user_locale if user_locale is not None else "ru", is_bot=is_bot)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def update_user(session: AsyncSession, user_id: int, first_name: str | None = None, last_name: str | None = None,
                      username: str | None = None, user_locale: str | None = None, is_bot: bool | None = None) -> User:
    user = await get_user(session, user_id)
    if user is None:
        raise ValueError(f"User with id {user_id} not found")
    if first_name is not None:
        user.first_name = first_name
    if last_name is not None:
        user.last_name = last_name
    if username is not None:
        user.username = username
    if locale is not None:
        user.locale = user_locale
    if is_bot is not None:
        user.is_bot = is_bot
    await session.commit()
    await session.refresh(user)
    return user


async def get_group_admins(session: AsyncSession, group_id: int) -> Sequence[User]:
    result = await session.execute(
        select(User)
        .join(GroupMember, GroupMember.user_id == User.id)
        .where(
            (GroupMember.group_id == group_id)
            &
            (GroupMember.is_active_admin == True)
            &
            (User.is_bot == False)
        )
    )
    return result.scalars().all()


async def get_locale(session: AsyncSession, user_id: int) -> str:
    return (await session.execute(select(User.locale).where(User.id == user_id))).scalar_one()
