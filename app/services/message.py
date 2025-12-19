from loguru import logger
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.message import Message
from app.db.repositories import message as message_repo


class MessageService:
    def __init__(self, session: async_sessionmaker):
        self.session = session

    async def get_message(self, group_id: int, message_id: int) -> Message | None:
        async with self.session() as session:
            message = await message_repo.get_message(session, group_id=group_id, message_id=message_id)
        return message

    async def create_message(self, group_id: int, message_id: int, is_watched: bool | None = None,
                             is_pinned: bool | None = None, text: str | None = None):
        async with self.session() as session:
            message = await message_repo.create_message(session, group_id=group_id, message_id=message_id,
                                                        is_watched=is_watched, is_pinned=is_pinned, text=text)
        return message

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