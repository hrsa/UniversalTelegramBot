from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.models.group import Group
from app.schemas.literals import GroupStatus, GroupType


async def get_or_create_group(
        session: AsyncSession,
        group_id: int,
        group_type: GroupType | None = None,
        title: str | None = None,
        status: str | None = None,
) -> Group:
    group = await get_group(session=session, group_id=group_id)
    if group is None:
        group = await create_group(session=session, group_id=group_id, group_type=group_type, title=title,
                                   status=status)
    return group


async def get_group(session: AsyncSession, group_id: int) -> Group | None:
    result = await session.execute(select(Group).where(Group.id == group_id))
    return result.scalar_one_or_none()

async def delete_group(session: AsyncSession, group_id: int) -> None:
    stmt = select(Group).where(Group.id == group_id)
    result = await session.execute(stmt)
    group = result.scalar_one_or_none()
    if group is not None:
        await session.delete(group)
        await session.commit()


async def create_group(session: AsyncSession, group_id: int, group_type: GroupType | None = None,
                       title: str | None = None,
                       status: str | None = None, ) -> Group:
    group = await get_group(session=session, group_id=group_id)
    if group is not None:
        raise ValueError(f"Group with id {group_id} already exists")
    group = Group(
        id=group_id,
        type=group_type,
        title=title,
        status=status if status is not None else "active"
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group


async def update_group(session: AsyncSession, group_id: int, new_group_id: int | None = None, title: str | None = None,
                       group_type: GroupType | None = None, status: GroupStatus | None = None,
                       greeting_hashtag: str | None = None,
                       greeting_message: str | None = None, reminder_message: str | None = None) -> Group:
    group = await get_or_create_group(session, group_id, group_type, title)

    group.id = new_group_id if new_group_id is not None else group.id
    group.type = group_type if group_type is not None else group.type
    group.status = status if status is not None else group.status
    group.greeting_hashtag = greeting_hashtag if greeting_hashtag is not None else group.greeting_hashtag
    group.greeting_message = greeting_message if greeting_message is not None else group.greeting_message
    group.reminder_message = reminder_message if reminder_message is not None else group.reminder_message
    await session.commit()
    await session.refresh(group)
    return group


async def get_active_groups(session: AsyncSession) -> Sequence[Group]:
    result = await session.execute(select(Group).where(Group.status == "active"))
    groups = result.scalars().all()
    return groups


async def set_group_status(session: AsyncSession, group_id: int, status: GroupStatus) -> Group:
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


# async def set_group_greeting(session: AsyncSession, group_id: int, hashtag: str, message: str) -> Group:
#     group = await get_or_create_group(session, group_id)
#
#     group.greeting_hashtag = hashtag
#     group.greeting_message = message
#
#     await session.commit()
#     await session.refresh(group)
#     return group
#
#
# async def set_reminder_message(session: AsyncSession, group_id: int, reminder_message: str) -> Group:
#     group = await get_or_create_group(session, group_id)
#     group.reminder_message = reminder_message
#     await session.commit()
#     await session.refresh(group)
#     return group


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


async def get_groups_eligible_for_invitation(session: AsyncSession, user_id: int, main_group_id: int) -> Sequence[
    Group]:
    stmt = (select(Group)
            .where(Group.type.in_({"supergroup", "group"}))
            .where(Group.id != main_group_id)
            .where((Group.members.any(user_id=user_id))
                   &
                   (Group.members.any(is_active_admin=True)))
            .where(Group.permissions.has(can_invite_users=True))
            )
    result = await session.execute(stmt)
    groups = result.scalars().all()
    return groups
