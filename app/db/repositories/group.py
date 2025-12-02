from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.models.group import Group


async def get_or_create_group(
        session: AsyncSession,
        group_id: int,
        type: str | None = None,
        title: str | None = None,
        status: str | None = None,
) -> Group:
    result = await session.execute(
        select(Group).where(Group.id == group_id)
    )
    group = result.scalar_one_or_none()

    if group is None:
        group = Group(
            id=group_id,
            type=type,
            title=title,
            status=status if status is not None else "active"
        )
        session.add(group)
        await session.commit()
    else:
        update_needed = False
        if type is not None and type != group.type:
            group.type = type
            update_needed = True
        if title is not None and title != group.title:
            group.title = title
            update_needed = True
        if status is not None and status != group.status:
            group.status = status
            update_needed = True
        if update_needed:
            await session.commit()
    await session.refresh(group)
    return group


async def set_group_status(session: AsyncSession, group_id: int, status: str) -> Group:
    group = await get_or_create_group(session, group_id)
    group.status = status
    await session.commit()
    await session.refresh(group)
    return group


async def set_group_features(session: AsyncSession, group_id: int, features: dict) -> Group:
    group = await get_or_create_group(session, group_id)
    group.features = features
    await session.commit()
    await session.refresh(group)
    return group


async def set_group_greeting(session: AsyncSession, group_id: int, hashtag: str, message: str) -> Group:
    group = await get_or_create_group(session, group_id)

    group.greeting_hashtag = hashtag
    group.greeting_message = message

    await session.commit()
    await session.refresh(group)
    return group

async def set_reminder_message(session: AsyncSession, group_id: int, reminder_message: str) -> Group:
    group = await get_or_create_group(session, group_id)
    group.reminder_message = reminder_message
    await session.commit()
    await session.refresh(group)
    return group


async def get_user_groups(session: AsyncSession, user_id: int) -> Sequence[Group]:
    result = await session.execute(select(Group).where(Group.members.any(user_id=user_id)))
    groups = result.scalars().all()
    return groups


async def get_groups_managed_by_user(session: AsyncSession, user_id: int) -> Sequence[Group]:
    result = await session.execute(select(Group)
    .where(
        (Group.members.any(user_id=user_id))
        &
        (Group.members.any(is_active_admin=True))
    ))
    groups = result.scalars().all()
    return groups
