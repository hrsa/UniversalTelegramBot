from datetime import datetime
from typing import Sequence, cast

from aiogram.types import message_id
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped

from app.bot.core import bot
from app.db.models.message import Message
from app.db.repositories import message as message_repo
from app.db.repositories import message_button as button_repo
from app.schemas.callbacks import AnnouncementCallback, AnnouncementAction


class MessageService:
    def __init__(self, session: async_sessionmaker):
        self.session = session

    async def get_message(self, announcement_id: int | None = None, group_id: int | None = None,
                          message_id: int | None = None) -> Message | None:
        async with self.session() as session:
            return await message_repo.get_message(session, announcement_id=announcement_id, group_id=group_id,
                                                  message_id=message_id)

    async def create_message(self, group_id: int, message_id: int | None = None, topic_id: int | None = None,
                             is_pinned: bool | None = None, is_published: bool | None = None, text: str | None = None,
                             picture: str | None = None):
        async with self.session() as session:
            return await message_repo.create_message(session, group_id=group_id, message_id=message_id,
                                                     topic_id=topic_id,
                                                     is_pinned=is_pinned, is_published=is_published, text=text,
                                                     picture=picture)

    async def pin_message(self, group_id: int, message_id: int):
        return await self.update_message(group_id=group_id, message_id=message_id, is_pinned=True)

    async def unpin_message(self, group_id: int, message_id: int):
        return await self.update_message(group_id=group_id, message_id=message_id, is_pinned=False)

    async def is_pinned(self, group_id: int, message_id: int) -> bool:
        message = await self.get_message(group_id=group_id, message_id=message_id)
        if message is None:
            raise ValueError(f"Message with id {message_id} not found in group {group_id}")
        return message.is_pinned

    async def delete_message(self, announcement_id: int | Mapped[int] | None = None,
                             group_id: int | Mapped[int] | None = None,
                             message_id: int | Mapped[int] | None = None):
        if announcement_id is None and group_id is None and message_id is None:
            raise ValueError("At least one of announcement_id, group_id, or message_id must be provided")
        async with self.session() as session:
            await message_repo.delete_message(session, group_id=group_id, message_id=message_id)

    async def update_message(self, announcement_id: int | Mapped[int] | None = None, group_id: int | None = None,
                             message_id: int | None = None,
                             topic_id: int | None = None, is_published: bool | None = None, text: str | None = None,
                             picture: str | None = None, is_pinned: bool | None = None):
        if announcement_id is None and group_id is None and message_id is None:
            raise ValueError("At least one of announcement_id, group_id, or message_id must be provided")
        async with self.session() as session:
            return await message_repo.update_message(session, announcement_id=announcement_id, group_id=group_id,
                                                     message_id=message_id,
                                                     topic_id=topic_id, is_published=is_published, text=text,
                                                     picture=picture, is_pinned=is_pinned)

    async def add_buttons_to_announcement(self, group_id: int | Mapped[int], message_id: int | Mapped[int]):
        message = await self.get_message(group_id=group_id, message_id=message_id)
        if message is None:
            raise ValueError(f"Message with id {message_id} not found in group {group_id}")
        async with self.session() as session:
            buttons = await button_repo.get_message_buttons(session, message.id)

        builder = InlineKeyboardBuilder()
        if buttons:
            for button in buttons:
                builder.button(text=button.text, url=button.link)
        builder.adjust(1)
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
