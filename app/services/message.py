from datetime import datetime
from typing import Sequence, cast

from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped

from app.bot.core import bot
from app.db.models.message import Message
from app.db.models.payment import Payment
from app.db.repositories import message as message_repo
from app.db.repositories import payment as payment_repo
from app.db.repositories import reward as reward_repo
from app.schemas.callbacks import AnnouncementCallback, AnnouncementAction


async def get_payment_counts(announcement: Message) -> tuple[int, int, int, int]:
    pending_payments_count = len(list(filter(lambda payment: payment.status == "pending", announcement.payments)))
    waiting_payments_count = len(list(filter(lambda payment: payment.status == "waiting", announcement.payments)))
    confirmed_payments_count = len(list(filter(lambda payment: payment.status == "paid", announcement.payments)))
    expired_payments_count = len(list(filter(lambda payment: payment.status == "expired", announcement.payments)))
    return confirmed_payments_count, expired_payments_count, pending_payments_count, waiting_payments_count


class MessageService:
    def __init__(self, session: async_sessionmaker):
        self.session = session

    async def get_message(self, announcement_id: int | None = None, group_id: int | None = None,
                          message_id: int | None = None, with_rewards: bool = False,
                          with_reward_groups: bool = False, with_payments: bool = False) -> Message | None:
        async with self.session() as session:
            message = await message_repo.get_message(session, announcement_id=announcement_id, group_id=group_id,
                                                     message_id=message_id, with_rewards=with_rewards,
                                                     with_reward_groups=with_reward_groups, with_payments=with_payments)
        return message

    async def create_message(self, group_id: int, message_id: int,
                             is_pinned: bool | None = None, text: str | None = None,
                             stripe_product_id: str | None = None, early_bird_stripe_product_id: str | None = None,
                             participants_limit: int | None = None):
        async with self.session() as session:
            message = await message_repo.create_message(session, group_id=group_id, message_id=message_id,
                                                        is_pinned=is_pinned, text=text,
                                                        stripe_product_id=stripe_product_id,
                                                        early_bird_stripe_product_id=early_bird_stripe_product_id,
                                                        participants_limit=participants_limit)
        return message

    async def get_expired_messages(self) -> Sequence[Message]:
        async with self.session() as session:
            return await message_repo.get_expired_messages(session)

    async def pin_message(self, group_id: int, message_id: int):
        async with self.session() as session:
            message = await message_repo.pin_message(session, group_id=group_id, message_id=message_id)
        return message

    async def unpin_message(self, group_id: int, message_id: int):
        async with self.session() as session:
            message = await message_repo.pin_message(session, group_id=group_id, message_id=message_id, unpin=True)
        return message

    async def is_pinned(self, group_id: int, message_id: int) -> bool:
        message = await self.get_message(group_id=group_id, message_id=message_id)
        if message is None:
            raise ValueError(f"Message with id {message_id} not found in group {group_id}")
        return message.is_pinned

    async def delete_message(self, group_id: int, message_id: int):
        async with self.session() as session:
            await message_repo.delete_message(session, group_id=group_id, message_id=message_id)

    async def update_text(self, group_id: int, message_id: int, text: str):
        async with self.session() as session:
            await message_repo.update_message(session, group_id=group_id, message_id=message_id, text=text)

    async def set_stripe_product_id(self, group_id: int, message_id: int, stripe_product_id: str):
        async with self.session() as session:
            await message_repo.update_message(session, group_id=group_id, message_id=message_id,
                                              stripe_product_id=stripe_product_id)

    async def set_early_bird_stripe_product_id(self, group_id: int, message_id: int, early_bird_stripe_product_id: str):
        async with self.session() as session:
            await message_repo.update_message(session, group_id=group_id, message_id=message_id,
                                              early_bird_stripe_product_id=early_bird_stripe_product_id)

    async def set_expiration_date(self, group_id: int, message_id: int, expiration_date: str):
        expiration_date = datetime.strptime(expiration_date, '%Y/%m/%d')
        if expiration_date < datetime.now():
            raise ValueError("Expiration date cannot be in the past.")
        async with self.session() as session:
            await message_repo.update_message(session, group_id=group_id, message_id=message_id,
                                              payment_expires_at=expiration_date)

    async def set_participants_limit(self, group_id: int, message_id: int, participants_limit: int):
        announcement = await self.get_message(group_id=group_id, message_id=message_id)
        async with self.session() as session:
            pending_payments = await payment_repo.get_payment_count(session=session, announcement_id=announcement.id,
                                                                    status="pending")
            confirmed_payments = await payment_repo.get_payment_count(session=session, announcement_id=announcement.id,
                                                                      status="paid")
            actual_limit = pending_payments + confirmed_payments
            if participants_limit < actual_limit:
                raise ValueError(f"You cannot set the participants limit to be lower than {actual_limit}.\n"
                                 f"There are {pending_payments} pending participants and {confirmed_payments} confirmed participants")
            else:
                await message_repo.update_message(session, group_id=group_id, message_id=message_id,
                                                  participants_limit=participants_limit)

    async def get_product_id(self, group_id: int, message_id: int) -> str | None:
        message = await self.get_message(group_id=group_id, message_id=message_id)
        if message is None:
            raise ValueError(f"Message with id {message_id} not found in group {group_id}")
        if message.stripe_product_id is None:
            raise ValueError(f"Stripe product id for message {message_id} not found")

        if message.participants_limit is None or message.early_bird_stripe_product_id is None:
            return message.stripe_product_id

        async with self.session() as session:
            payment_count = await payment_repo.get_payment_count(session, message_id)

        early_bird_limit = int(message.participants_limit * 0.3 + 0.5)

        return message.early_bird_stripe_product_id if early_bird_limit <= payment_count else message.stripe_product_id

    async def get_participants(self, announcement_id: int | None = None, message_id: int | None = None, group_id: int | None = None) -> Sequence[Payment] | None:
        async with self.session() as session:
            message = await message_repo.get_participants(session, announcement_id=announcement_id, message_id=message_id, group_id=group_id)
            return cast(Sequence[Payment], message.payments) if message is not None else None

    async def add_button_to_announcement(self, group_id: int, message_id: int, button_text: str,
                                         action: AnnouncementAction = AnnouncementAction.join,
                                         event_name: str | None = None):
        message = await self.get_message(group_id=group_id, message_id=message_id)
        if message is None:
            raise ValueError(f"Message with id {message_id} not found in group {group_id}")

        if message.stripe_product_id is None and message.early_bird_stripe_product_id is None:
            raise ValueError(f"Stripe product id for message {message_id} not found")

        builder = InlineKeyboardBuilder()
        builder.button(text=button_text,
                       callback_data=AnnouncementCallback(action=action, announcement_id=message.id,
                                                          event_name=event_name).pack())

        try:
            await bot.edit_message_reply_markup(chat_id=group_id, message_id=message_id,
                                                reply_markup=builder.as_markup())
        except Exception as e:
            logger.error(e)

    async def remove_button_from_announcement(self, group_id: int, message_id: int):
        message = await self.get_message(group_id=group_id, message_id=message_id)
        if message is None:
            raise ValueError(f"Message with id {message_id} not found in group {group_id}")

        builder = InlineKeyboardBuilder()

        try:
            await bot.edit_message_reply_markup(chat_id=group_id, message_id=message_id,
                                                reply_markup=builder.as_markup())
        except Exception as e:
            logger.error(e)

    async def remove_payment_product(self, group_id: int | Mapped[int] | None = None, message_id: int | Mapped[int] | None = None,
                                     announcement_id: int | Mapped[int] | None = None):
        message = await self.get_message(group_id=group_id, message_id=message_id, announcement_id=announcement_id, with_payments=True, with_rewards=True)
        if message is None:
            raise ValueError(f"Announcement with id {announcement_id}, message_id {message_id} not found in group {group_id}")
        async with self.session() as session:
            if message.payments:
                confirmed, expired, pending, waiting = await get_payment_counts(message)
                if confirmed + pending + waiting > 0:
                    raise ValueError("You cannot remove the payment product because there are payments associated with it.")
                else:
                    for payment in message.payments:
                            await payment_repo.delete_payment(session, payment.id)
            if message.reward:
                await reward_repo.delete_reward(session, reward_id=message.reward.id)

            await message_repo.remove_payment_product(session, announcement_id=message.id, early_bird_only=False)


    async def remove_early_bird_payment_product(self, group_id: int | Mapped[int] | None = None, message_id: int | Mapped[int] | None = None,
                                     announcement_id: int | Mapped[int] | None = None):
        message = await self.get_message(group_id=group_id, message_id=message_id, announcement_id=announcement_id, with_payments=True, with_rewards=True)
        if message is None:
            raise ValueError(f"Announcement with id {announcement_id}, message_id {message_id} not found in group {group_id}")

        async with self.session() as session:
            await message_repo.remove_payment_product(session, announcement_id=message.id, early_bird_only=True)
