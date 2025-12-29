from datetime import datetime, timezone
from typing import Sequence

from loguru import logger
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.db.models.message import Message
from app.db.models.payment import Payment
from app.db.models.reward import Reward
from app.db.models.user import User


async def get_message(session: AsyncSession, announcement_id: int | None = None, group_id: int | None = None,
                      message_id: int | None = None, with_rewards: bool = False, with_reward_groups: bool = False,
                      with_payments: bool = False) -> Message | None:
    stmt = select(Message)
    if with_rewards:
        if with_reward_groups:
            stmt = stmt.options(selectinload(Message.reward).selectinload(Reward.group))
        else:
            stmt = stmt.options(selectinload(Message.reward))
    if with_payments:
        stmt = stmt.options(selectinload(Message.payments))
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
        message_id: int,
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


async def delete_message(session: AsyncSession, group_id: int, message_id: int):
    message = await get_message(session=session, group_id=group_id, message_id=message_id, with_rewards=True, with_payments=True)
    if message:
        if message.reward:
            await session.delete(message.reward)
        if message.payments and len(message.payments) > 0:
            for payment in message.payments:
                await session.delete(payment)
        await session.delete(message)
        await session.commit()


async def get_messages_for_group(session: AsyncSession, group_id: int, offset: int = 0, limit: int = 0,
                                 with_rewards: bool = False, with_reward_groups: bool = False,
                                 with_payments: bool = False) -> tuple[
    Sequence[Message], int]:
    stmt = select(Message)
    if with_rewards:
        if with_reward_groups:
            stmt = stmt.options(selectinload(Message.reward).selectinload(Reward.group))
        else:
            stmt = stmt.options(selectinload(Message.reward))
    if with_payments:
        stmt = stmt.options(selectinload(Message.payments))

    stmt = (stmt.where(Message.group_id == group_id)
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
                         group_id: int,
                         message_id: int,
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
    message.is_pinned = is_pinned if is_pinned is not None else message.is_pinned
    message.text = text if text is not None else message.text
    message.stripe_product_id = stripe_product_id if stripe_product_id is not None else message.stripe_product_id
    message.early_bird_stripe_product_id = early_bird_stripe_product_id if early_bird_stripe_product_id is not None else message.early_bird_stripe_product_id
    message.payment_expires_at = payment_expires_at if payment_expires_at is not None else message.payment_expires_at
    message.participants_limit = participants_limit if participants_limit is not None else message.participants_limit
    await session.commit()
    await session.refresh(message)
    return message


async def remove_payment_product(session: AsyncSession, group_id: int | None = None, message_id: int | None = None,
                                 announcement_id: int | None = None, early_bird_only: bool = False):
    message = await get_message(session=session, group_id=group_id, message_id=message_id,
                                announcement_id=announcement_id)
    if message is None:
        raise ValueError(f"Message with id {message_id} not found in group {group_id}")
    if not early_bird_only:
        message.stripe_product_id = None
        message.payment_expires_at = None
        message.participants_limit = None
    message.early_bird_stripe_product_id = None
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

async def get_participants(session: AsyncSession, announcement_id: int | None = None, message_id: int | None = None, group_id: int | None = None) -> Message | None:
    stmt = (select(Message)
            .options(selectinload(Message.payments).selectinload(Payment.user)))
    if announcement_id:
        stmt = stmt.where(Message.id == announcement_id)
    elif message_id and group_id:
        stmt = stmt.where(Message.message_id == message_id).where(Message.group_id == group_id)
    else:
        return None


    result = await session.execute(stmt)
    return result.scalars().one_or_none()