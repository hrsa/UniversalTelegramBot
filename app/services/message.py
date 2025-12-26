from datetime import datetime
from typing import Sequence

from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.core import bot
from app.db.models.message import Message
from app.db.repositories import message as message_repo
from app.db.repositories import payment as payment_repo
from app.handlers.admin.callbacks import AnnouncementCallback, AnnouncementAction


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

    async def create_message(self, group_id: int, message_id: int, is_watched: bool | None = None,
                             is_pinned: bool | None = None, text: str | None = None,
                             stripe_product_id: str | None = None):
        async with self.session() as session:
            message = await message_repo.create_message(session, group_id=group_id, message_id=message_id,
                                                        is_watched=is_watched, is_pinned=is_pinned, text=text,
                                                        stripe_product_id=stripe_product_id)
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

    async def watch_message(self, group_id: int, message_id: int):
        async with self.session() as session:
            message = await message_repo.watch_message(session, group_id=group_id, message_id=message_id)
        return message

    async def unwatch_message(self, group_id: int, message_id: int):
        async with self.session() as session:
            message = await message_repo.watch_message(session, group_id=group_id, message_id=message_id, unwatch=True)
        return message

    async def is_watched(self, group_id: int, message_id: int) -> bool:
        message = await self.get_message(group_id=group_id, message_id=message_id)
        if message is None:
            raise ValueError(f"Message with id {message_id} not found in group {group_id}")
        return message.is_watched

    async def is_pinned(self, group_id: int, message_id: int) -> bool:
        message = await self.get_message(group_id=group_id, message_id=message_id)
        if message is None:
            raise ValueError(f"Message with id {message_id} not found in group {group_id}")
        return message.is_pinned

    async def delete_message(self, group_id: int, message_id: int):
        async with self.session() as session:
            await message_repo.delete_message(session, group_id=group_id, message_id=message_id)

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
        async with self.session() as session:
            await message_repo.update_message(session, group_id=group_id, message_id=message_id,
                                              participants_limit=participants_limit)

    async def get_product_id(self, group_id: int, message_id: int) -> str | None:
        message = await self.get_message(group_id=group_id, message_id=message_id)
        if message is None:
            raise ValueError(f"Message with id {message_id} not found in group {group_id}")

        if message.participants_limit is None:
            return message.stripe_product_id

        async with self.session() as session:
            payment_count = await payment_repo.get_payment_count(session, message_id)

        early_bird_limit = int(message.participants_limit * 0.3 + 0.5)

        return message.early_bird_stripe_product_id if early_bird_limit <= payment_count else message.stripe_product_id

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
