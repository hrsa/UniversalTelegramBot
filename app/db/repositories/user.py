import locale

from sqlalchemy import Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import Mapped, selectinload

from app.db.models.group_member import GroupMember
from app.db.models.user import User


async def get_or_create_user(
        session: AsyncSession,
        user_id: int,
        first_name: str | None = None,
        last_name: str | None = None,
        username: str | None = None,
        email: str | None = None,
        user_locale: str | None = None,
        is_bot: bool | None = False,
) -> User:
    user = await get_user(session=session, user_id=user_id)
    if user is None:
        user = await create_user(session=session, user_id=user_id, first_name=first_name, last_name=last_name,
                                 username=username, user_locale=user_locale, is_bot=is_bot, email=email)
    return user


async def create_user(session: AsyncSession, user_id: int, first_name: str | None = None, last_name: str | None = None,
                      username: str | None = None, email: str | None = None, user_locale: str | None = None,
                      is_bot: bool = False) -> User:
    user = User(id=user_id, first_name=first_name, last_name=last_name, username=username, email=email,
                locale=user_locale if user_locale is not None else "ru", is_bot=is_bot)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def find_users(session: AsyncSession, in_groups: list[int] | None = None,
                     user_id: int | Mapped[int] | None = None,
                     first_name: str | Mapped[str] | None = None, last_name: str | Mapped[str] | None = None,
                     username: str | Mapped[str] | None = None, email: str | Mapped[str] | None = None,
                     user_locale: str | Mapped[str] | None = None,
                     is_bot: bool | None = None) -> Sequence[User]:
    if all(value is None
           for value in (in_groups, user_id, first_name, last_name, username, email, user_locale, is_bot)
           ):
        raise ValueError("At least one search filter must be provided")

    stmt = select(User).options(selectinload(User.groups).selectinload(GroupMember.group))
    if in_groups is not None:
        if not in_groups:
            return []

        stmt = (
            stmt
            .join(GroupMember, GroupMember.user_id == User.id)
            .where(GroupMember.group_id.in_(in_groups))
        )
    if user_id is not None:
        stmt = stmt.where(User.id == user_id)
    if first_name is not None:
        stmt = stmt.where(User.first_name == first_name)
    if last_name is not None:
        stmt = stmt.where(User.last_name == last_name)
    if username is not None:
        stmt = stmt.where(User.username == username)
    if email is not None:
        stmt = stmt.where(User.email == email)
    if user_locale is not None:
        stmt = stmt.where(User.locale == user_locale)
    if is_bot is not None:
        stmt = stmt.where(User.is_bot == is_bot)

    result = await session.execute(stmt)
    return result.scalars().all()


async def update_user(session: AsyncSession, user_id: int, first_name: str | None = None, last_name: str | None = None,
                      username: str | None = None, email: str | None = None, user_locale: str | None = None,
                      is_bot: bool | None = None) -> User:
    user = await get_user(session, user_id)
    if user is None:
        raise ValueError(f"User with id {user_id} not found")
    
    updates = {
        'first_name': first_name,
        'last_name': last_name,
        'username': username,
        'locale': user_locale,
        'email': email,
        'is_bot': is_bot,
    }
    
    for field, value in updates.items():
        if value is not None:
            setattr(user, field, value)
    
    await session.commit()
    await session.refresh(user)
    return user


async def get_group_admins(session: AsyncSession, group_id: int | Mapped[int]) -> Sequence[User]:
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
