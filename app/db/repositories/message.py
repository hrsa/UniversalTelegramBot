from typing import Sequence

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.models.message import Message


async def get_message(session: AsyncSession, group_id: int, message_id: int) -> Message | None:
    result = await session.execute(
        select(Message).where(Message.group_id == group_id).where(Message.message_id == message_id))
    return result.scalar_one_or_none()

async def create_message(
        session: AsyncSession,
        group_id: int,
        message_id: int,
        is_watched: bool | None = None,
        is_pinned: bool | None = None,
        text: str | None = None,
) -> Message:
    message = await get_message(session, group_id, message_id)

    if message is not None:
        raise ValueError(f"Message with id {message_id} already exists in group {group_id}")

    message = Message(
        group_id=group_id,
        message_id=message_id,
        text=text,
        is_pinned=is_pinned if is_pinned is not None else False,
        is_watched=is_watched if is_watched is not None else False
    )
    session.add(message)
    await session.commit()

    await session.refresh(message)
    return message

async def pin_message(session: AsyncSession, group_id: int, message_id: int, unpin: bool = False) -> Message:
    message = await get_message(session, group_id, message_id)
    if unpin:
        message.is_pinned = False
    else:
        message.is_pinned = True
    await session.commit()
    await session.refresh(message)
    return message


async def watch_message(session: AsyncSession, group_id: int, message_id: int, unwatch: bool = False) -> Message:
    message = await get_message(session, group_id, message_id)
    if unwatch:
        message.is_watched = False
    else:
        message.is_watched = True
    await session.commit()
    await session.refresh(message)
    return message

async def delete_message(session: AsyncSession, group_id: int, message_id: int):
    message = await get_message(session, group_id, message_id)
    if message:
        await session.delete(message)
        await session.commit()


async def get_messages_for_group(session: AsyncSession, group_id: int, offset: int = 0, limit: int = 0) -> tuple[Sequence[Message], int]:
    msg_result = await session.execute(
        select(Message)
        .where(Message.group_id == group_id)
        .order_by(Message.created_at.desc())
        .offset(offset)
        .limit(limit))
    messages = msg_result.scalars().all()

    count_result = await session.execute(
        select(func.count(Message.id))
        .where(Message.group_id == group_id)
    )
    count = count_result.scalar_one() or 0
    return messages, count