from datetime import datetime
from typing import Sequence

from loguru import logger
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import Mapped

from app.db.models.payment import Payment
from app.schemas.literals import PaymentStatus


async def get_payment(session: AsyncSession, payment_id: int | Mapped[int] | None = None, user_id: int | Mapped[int] | None = None,
                      message_id: int | Mapped[int] | None = None, stripe_payment_id: str | None = None) -> Payment | None:
    if payment_id:
        stmt = select(Payment).where(Payment.id == payment_id)
    elif user_id and message_id:
        stmt = select(Payment).where(Payment.user_id == user_id).where(Payment.message_id == message_id)
    elif stripe_payment_id:
        stmt = select(Payment).where(Payment.stripe_payment_id == stripe_payment_id)
    else:
        return None

    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def get_payments(session: AsyncSession, user_id: int | None = None, message_id: int | None = None, status: PaymentStatus | None = None) -> Sequence[Payment]:
    stmt = select(Payment)
    if message_id:
        stmt = stmt.where(Payment.message_id == message_id)
    if status:
        stmt = stmt.where(Payment.status == status)
    if user_id:
        stmt = stmt.where(Payment.user_id == user_id)
    result = await session.execute(stmt.order_by(Payment.created_at.desc()))
    return result.scalars().all()



async def create_payment(
        session: AsyncSession,
        user_id: int | Mapped[int],
        message_id: int | Mapped[int],
        stripe_payment_id: str | None = None,
        stripe_product_id: str | None = None,
        status: PaymentStatus | None = None,
        url: str | None = None,
        amount: int | None = None,
) -> Payment:
    payment = await get_payment(session, user_id=user_id, message_id=message_id, stripe_payment_id=stripe_payment_id)
    if payment is not None:
        raise ValueError(f"Payment for user {user_id} and message {message_id} and stripe_payment_id {stripe_payment_id} already exists")

    payment = Payment(
        user_id=user_id,
        message_id=message_id,
        stripe_payment_id=stripe_payment_id,
        stripe_product_id=stripe_product_id,
        status=status if status is not None else "pending",
        url=url,
        amount=amount,
    )
    session.add(payment)
    await session.commit()

    await session.refresh(payment)
    return payment


async def update_payment(session: AsyncSession,
                         payment_id: int | Mapped[int] | None = None,
                         user_id: int | Mapped[int] | None = None,
                         message_id: int | Mapped[int] | None = None,
                         stripe_payment_id: str | None = None,
                         stripe_product_id: str | None = None,
                         status: PaymentStatus | None = None,
                         url: str | None = None,
                         amount: int | None = None,
                         created_at: datetime | None = None,
                         claimed_at: datetime | None = None) -> Payment:
    payment = await get_payment(session, payment_id=payment_id, user_id=user_id, message_id=message_id, stripe_payment_id=stripe_payment_id)
    if payment is None:
        raise ValueError(f"Payment for user {user_id} and message {message_id} and stripe_payment_id {stripe_payment_id} not found")

    payment.status = status if status is not None else payment.status
    payment.stripe_product_id = stripe_product_id if stripe_product_id is not None else payment.stripe_product_id
    payment.stripe_payment_id = stripe_payment_id if stripe_payment_id is not None else payment.stripe_payment_id
    payment.url = url if url is not None else payment.url
    payment.amount = amount if amount is not None else payment.amount
    payment.claimed_at = claimed_at if claimed_at is not None else payment.claimed_at
    payment.created_at = created_at if created_at is not None else payment.created_at

    await session.commit()
    await session.refresh(payment)
    return payment

async def delete_payment(session: AsyncSession, payment_id: int | Mapped[int]):
    payment = await get_payment(session, payment_id=payment_id)
    if payment is not None:
        await session.delete(payment)
        await session.commit()



async def get_payment_count(session: AsyncSession, announcement_id: int | Mapped[int], status: PaymentStatus | None = None) -> int:
    stmt = select(func.count(Payment.id)).where(Payment.message_id == announcement_id)
    if status is not None:
        stmt = stmt.where(Payment.status == status)
    result = await session.execute(stmt)
    return result.scalar_one()
