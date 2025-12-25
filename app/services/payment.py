from datetime import datetime
from typing import Sequence

from loguru import logger
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped

from app.db.models.payment import Payment
from app.db.repositories import payment as payment_repo
from app.schemas.literals import PaymentStatus
from app.services.message import MessageService
from app.services.stripe_payment import StripePaymentService


class PaymentService:
    def __init__(self, session: async_sessionmaker, message_service: MessageService):
        self.session = session
        self.stripe_service = StripePaymentService()
        self.message_service = message_service

    async def get_payment(self, payment_id: int | None = None, user_id: int | None = None,
                          announcement_id: int | None = None, stripe_payment_id: str | None = None) -> Payment | None:
        async with self.session() as session:
            payment = await payment_repo.get_payment(session, payment_id=payment_id, user_id=user_id,
                                                     message_id=announcement_id, stripe_payment_id=stripe_payment_id)
        return payment

    async def get_payments(self, user_id: int | None = None, announcement_id: int | None = None,
                           status: PaymentStatus | None = None) -> Sequence[Payment]:
        async with self.session() as session:
            return await payment_repo.get_payments(session, user_id=user_id, message_id=announcement_id, status=status)

    async def create_payment(self, user_id: int | Mapped[int],
                             group_id: int | Mapped[int],
                             message_id: int | Mapped[int],
                             status: PaymentStatus | None = None):
        announcement = await self.message_service.get_message(group_id=group_id, message_id=message_id)
        stripe_product_id = await self.message_service.get_product_id(group_id=group_id, message_id=message_id)

        if stripe_product_id is None:
            raise ValueError(f"Stripe product id for message {announcement.id} not found")

        async with self.session() as session:
            payment_link = await self.stripe_service.create_payment_link(user_id=user_id, product_id=stripe_product_id)
            amount = await self.stripe_service.get_price(stripe_product_id)

            logger.warning(payment_link)

            payment = await payment_repo.create_payment(session, user_id=user_id, message_id=announcement.id,
                                                        stripe_payment_id=payment_link.id,
                                                        stripe_product_id=stripe_product_id,
                                                        status=status if status is not None else "pending",
                                                        url=payment_link.url,
                                                        amount=amount)
        return payment

    async def update_payment(self, user_id: int | None = None,
                             announcement_id: int | None = None,
                             stripe_payment_id: str | None = None,
                             stripe_product_id: str | None = None,
                             status: PaymentStatus | None = None,
                             url: str | None = None,
                             amount: int | None = None,
                             claimed_at: datetime | None = None,
                             created_at: datetime | None = None
                             ):
        async with self.session() as session:
            payment = await payment_repo.update_payment(session, user_id=user_id, message_id=announcement_id,
                                                        stripe_payment_id=stripe_payment_id,
                                                        stripe_product_id=stripe_product_id,
                                                        status=status, url=url,
                                                        amount=amount, claimed_at=claimed_at, created_at=created_at)
        return payment

    async def get_payment_count(self, announcement_id: int, status: PaymentStatus | None = None) -> int:
        async with self.session() as session:
            return await payment_repo.get_payment_count(session=session, announcement_id=announcement_id, status=status)

    async def verify_event_capacity(self, announcement_id: int):
        announcement = await self.message_service.get_message(announcement_id=announcement_id)
        confirmed = await self.get_payment_count(announcement_id, "paid")
        pending = await self.get_payment_count(announcement_id, "pending")
        limit = announcement.participants_limit
        is_full = limit and (confirmed + pending) >= limit

        return is_full, pending
