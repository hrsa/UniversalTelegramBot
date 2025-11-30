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
        is_bot: bool |None = None,
) -> User:
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            id=user_id,
            first_name=first_name,
            last_name=last_name,
            username=username,
            is_bot=is_bot if is_bot is not None else False
        )
        session.add(user)
        await session.commit()
    else:
        update_needed = False
        if first_name is not None and first_name != user.first_name:
            user.first_name = first_name
            update_needed = True
        if last_name is not None and last_name != user.last_name:
            user.last_name = last_name
            update_needed = True
        if username is not None and username != user.username:
            user.username = username
            update_needed = True
        if is_bot is not None and is_bot != user.is_bot:
            user.is_bot = is_bot
            update_needed = True
        if update_needed:
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
        )
    )
    return result.scalars().all()
