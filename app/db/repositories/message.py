from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.models.message import Message


async def get_message(session: AsyncSession, announcement_id: int | None = None, group_id: int | None = None,
                      message_id: int | None = None) -> Message | None:
    stmt = select(Message)
    if announcement_id:
        stmt = stmt.where(Message.id == announcement_id)
    elif group_id and message_id:
        stmt = stmt.where(Message.group_id == group_id).where(Message.message_id == message_id)
    else:
        return None
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_message(
        session: AsyncSession,
        group_id: int,
        message_id: int | None,
        topic_id: int | None = None,
        is_published: bool = False,
        is_pinned: bool | None = None,
        text: str | None = None,
        picture: str | None = None,
) -> Message:

    if group_id is not None and message_id is not None:
        message = await get_message(session=session, group_id=group_id, message_id=message_id)
        if message is not None:
            raise ValueError(f"Message with id {message_id} already exists in group {group_id}")

    message = Message(
        group_id=group_id,
        message_id=message_id,
        topic_id=topic_id,
        is_published=is_published,
        text=text,
        picture=picture,
        is_pinned=is_pinned if is_pinned is not None else False,
    )
    session.add(message)
    await session.commit()

    await session.refresh(message)
    return message


async def delete_message(session: AsyncSession, announcement_id: int | None = None, group_id: int | None = None, message_id: int | None = None):
    message = await get_message(session=session, announcement_id=announcement_id, group_id=group_id, message_id=message_id)
    if message:
        await session.delete(message)
        await session.commit()


async def get_messages_for_group(session: AsyncSession, group_id: int, offset: int = 0, limit: int = 0) -> tuple[
    Sequence[Message], int]:
    stmt = (select(Message)
            .where(Message.group_id == group_id)
            .order_by(Message.created_at.desc()))

    if offset > 0:
        stmt = stmt.offset(offset)
    if limit > 0:
        stmt = stmt.limit(limit)

    msg_result = await session.execute(stmt)
    messages = msg_result.scalars().all()
    count_result = await session.execute(
        select(func.count(Message.id))
        .where(Message.group_id == group_id)
    )
    count = count_result.scalar_one() or 0
    return messages, count


async def update_message(session: AsyncSession,
                         announcement_id: int | None,
                         group_id: int | None,
                         message_id: int | None = None,
                         topic_id: int | None = None,
                         is_published: bool | None = None,
                         is_pinned: bool | None = None,
                         text: str | None = None,
                         picture: str | None = None,
                         ):
    if announcement_id is not None:
        message = await get_message(session=session, announcement_id=announcement_id)
    elif group_id is not None and message_id is not None:
        message = await get_message(session=session, group_id=group_id, message_id=message_id)
    else:
        raise ValueError(f"Can't get announcement with id {announcement_id}, message_id {message_id}, group_id {group_id}")
    if message is None:
        raise ValueError(f"Message with id {message_id} not found in group {group_id}")
    message.is_pinned = is_pinned if is_pinned is not None else message.is_pinned
    message.group_id = group_id if group_id is not None else message.group_id
    message.message_id = message_id if message_id is not None else message.message_id
    message.is_published = is_published if is_published is not None else message.is_published
    message.topic_id = topic_id if topic_id is not None else message.topic_id
    message.text = text if text is not None else message.text
    message.picture = picture if picture is not None else message.picture
    await session.commit()
    await session.refresh(message)
    return message