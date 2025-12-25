from datetime import datetime, timezone
from typing import Sequence

from loguru import logger
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.models.message import Message
from app.db.models.payment import Payment


async def get_message(session: AsyncSession, announcement_id: int | None = None, group_id: int | None = None,
                      message_id: int | None = None) -> Message | None:
    logger.debug(f"Getting message with id {announcement_id} or group {group_id} and message {message_id}")
    if announcement_id:
        stmt = select(Message).where(Message.id == announcement_id)
    elif group_id and message_id:
        stmt = select(Message).where(Message.group_id == group_id).where(Message.message_id == message_id)
    else:
        return None
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_message(
        session: AsyncSession,
        group_id: int,
        message_id: int,
        is_watched: bool | None = None,
        is_pinned: bool | None = None,
        text: str | None = None,
        stripe_product_id: str | None = None,
        early_bird_stripe_product_id: str | None = None,
        payment_expires_at: datetime | None = None,
        participants_limit: int | None = None
) -> Message:
    message = await get_message(session=session, group_id=group_id, message_id=message_id)

    if message is not None:
        raise ValueError(f"Message with id {message_id} already exists in group {group_id}")

    message = Message(
        group_id=group_id,
        message_id=message_id,
        text=text,
        is_pinned=is_pinned if is_pinned is not None else False,
        is_watched=is_watched if is_watched is not None else False,
        stripe_product_id=stripe_product_id if stripe_product_id is not None else None,
        early_bird_stripe_product_id=early_bird_stripe_product_id if early_bird_stripe_product_id is not None else None,
        payment_expires_at=payment_expires_at if payment_expires_at is not None else None,
        participants_limit=participants_limit
    )
    session.add(message)
    await session.commit()

    await session.refresh(message)
    return message


async def pin_message(session: AsyncSession, group_id: int, message_id: int, unpin: bool = False) -> Message:
    message = await get_message(session=session, group_id=group_id, message_id=message_id)
    if unpin:
        message.is_pinned = False
    else:
        message.is_pinned = True
    await session.commit()
    await session.refresh(message)
    return message


async def watch_message(session: AsyncSession, group_id: int, message_id: int, unwatch: bool = False) -> Message:
    message = await get_message(session=session, group_id=group_id, message_id=message_id)
    if unwatch:
        message.is_watched = False
    else:
        message.is_watched = True
    await session.commit()
    await session.refresh(message)
    return message


async def delete_message(session: AsyncSession, group_id: int, message_id: int):
    message = await get_message(session=session, group_id=group_id, message_id=message_id)
    if message:
        await session.delete(message)
        await session.commit()


async def get_messages_for_group(session: AsyncSession, group_id: int, offset: int = 0, limit: int = 0) -> tuple[
    Sequence[Message], int]:
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


async def update_message(session: AsyncSession,
                         group_id: int,
                         message_id: int,
                         is_watched: bool | None = None,
                         is_pinned: bool | None = None,
                         text: str | None = None,
                         stripe_product_id: str | None = None,
                         early_bird_stripe_product_id: str | None = None,
                         payment_expires_at: datetime | None = None,
                         participants_limit: int | None = None
                         ):
    message = await get_message(session=session, group_id=group_id, message_id=message_id)
    if message is None:
        raise ValueError(f"Message with id {message_id} not found in group {group_id}")
    message.is_watched = is_watched if is_watched is not None else message.is_watched
    message.is_pinned = is_pinned if is_pinned is not None else message.is_pinned
    message.text = text if text is not None else message.text
    message.stripe_product_id = stripe_product_id if stripe_product_id is not None else message.stripe_product_id
    message.early_bird_stripe_product_id = early_bird_stripe_product_id if early_bird_stripe_product_id is not None else message.early_bird_stripe_product_id
    message.payment_expires_at = payment_expires_at if payment_expires_at is not None else message.payment_expires_at
    message.participants_limit = participants_limit if participants_limit is not None else message.participants_limit
    await session.commit()
    await session.refresh(message)
    return message


async def get_expired_messages(session: AsyncSession) -> Sequence[Message]:
    stmt = (select(Message)
            .where(Message.payment_expires_at.is_not(None))
            .where(Message.payment_expires_at <= datetime.now(timezone.utc)))
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_message_payments(session: AsyncSession, message_id: int) -> Sequence[Payment]:
    stmt = select(Payment).where(Payment.message_id == message_id)
    result = await session.execute(stmt)
    return result.scalars().all()
