from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql.functions import func

from app.db.models.group_member import GroupMember


async def get_or_create_group_member(
        session: AsyncSession,
        group_id: int,
        user_id: int,
        role: str | None = None,
        status: str | None = None,
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


async def set_member_status(session: AsyncSession, group_id: int, user_id, status: str) -> GroupMember:
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
    return group_member

async def get_members_without_greetings(session: AsyncSession, group_id: int) -> Sequence[GroupMember]:
    result = await session.execute(
        select(GroupMember).where(GroupMember.group_id == group_id).where(GroupMember.greeting_message is None)
    )
    group_members = result.scalars().all()
    return group_members