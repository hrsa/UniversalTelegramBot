from datetime import datetime
from typing import Sequence

from certifi import where
from sqlalchemy import exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import Mapped, selectinload
from sqlalchemy.sql.functions import func

from app.db.models.group import Group
from app.db.models.group_member import GroupMember
from app.db.models.user import User
from app.schemas.literals import UserRole, UserStatus


async def get_or_create_group_member(
        session: AsyncSession,
        group_id: int,
        user_id: int,
        role: UserRole | None = None,
        status: UserStatus | None = None,
) -> GroupMember:
    result = await session.execute(
        select(GroupMember).where((GroupMember.group_id == group_id) & (GroupMember.user_id == user_id))
    )
    group_member = result.scalar_one_or_none()

    if group_member is None:
        group_member = GroupMember(
            group_id=group_id,
            user_id=user_id,
            role=role if role is not None else "member",
            status=status if status is not None else "active",
        )

        if status == "active":
            group_member.joined_at = func.now()
        if status == "left":
            group_member.left_at = func.now()

        session.add(group_member)
        await session.commit()
    else:
        update_needed = False
        if role is not None and role != group_member.role:
            group_member.role = role
            update_needed = True
        if status is not None and status != group_member.status:
            group_member.status = status
            if status == "active":
                group_member.joined_at = func.now()
            if status == "left":
                group_member.left_at = func.now()
            update_needed = True
        if update_needed:
            await session.commit()

    await session.refresh(group_member)
    return group_member


async def is_admin(session: AsyncSession, user_id: int | Mapped[int]) -> bool:
    stmt = select(
        exists().where(
            GroupMember.user_id == user_id,
            GroupMember.status == "active",
            GroupMember.role.in_(["administrator", "creator"]),
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def set_member_status(session: AsyncSession, group_id: int, user_id: int, status: UserStatus) -> GroupMember:
    group_member = await get_or_create_group_member(session, group_id, user_id)
    group_member.status = status
    if status == "active":
        group_member.joined_at = func.now()
    if status == "left":
        group_member.left_at = func.now()
    await session.commit()
    await session.refresh(group_member)
    return group_member


async def set_member_greeting_message(session: AsyncSession, group_id: int, user_id: int, message: str) -> GroupMember:
    group_member = await get_or_create_group_member(session, group_id, user_id)
    group_member.greeting_message = message
    await session.commit()
    await session.refresh(group_member)
    return group_member


async def get_group_members(
        session: AsyncSession, group_id: int | Mapped[int], role: UserRole | None = None,
        status: UserStatus | None = None
) -> Sequence[GroupMember]:
    stmt = (select(GroupMember)
            .options(selectinload(GroupMember.user))
            .where(GroupMember.group_id == group_id)
            )

    if role is not None:
        stmt = stmt.where(GroupMember.role == role)

    if status is not None:
        stmt = stmt.where(GroupMember.status == status)

    result = await session.execute(stmt)
    group_members = result.scalars().all()
    return group_members


async def get_members_without_greetings(session: AsyncSession, group_id: int | None = None) -> Sequence[GroupMember]:
    stmt = select(GroupMember).join(Group, Group.id == GroupMember.group_id)
    stmt = stmt.where(GroupMember.greeting_message.is_(None))
    stmt = stmt.where(GroupMember.status == "active")

    stmt = stmt.where(Group.status == "active")
    stmt = stmt.where(Group.features.contains({"greeting_watch": True}))
    stmt = stmt.where(Group.greeting_message.is_not(None))
    stmt = stmt.where(Group.greeting_hashtag.is_not(None))
    stmt = stmt.where(Group.reminder_message.is_not(None))

    if group_id:
        stmt = stmt.where(GroupMember.group_id == group_id)

    result = await session.execute(stmt)
    group_members = result.scalars().all()
    return group_members


async def increase_warning_count(session: AsyncSession, group_id: int, user_id: int) -> GroupMember:
    group_member = await get_or_create_group_member(session, group_id, user_id)
    group_member.warning_count += 1
    await session.commit()
    await session.refresh(group_member)
    return group_member
