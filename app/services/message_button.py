from typing import Sequence

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.message_button import Button
from app.db.repositories import message_button as button_repo


class ButtonService:
    def __init__(self, session: async_sessionmaker):
        self.session = session

    async def get_button(self, button_id: int) -> Button | None:
        async with self.session() as session:
            return await button_repo.get_button(session, button_id)

    async def create_button(self, message_id: int, button_text: str, button_link: str) -> Button | None:
        async with self.session() as session:
            return await button_repo.create_button(session, message_id=message_id, text=button_text, link=button_link)

    async def update_button(self, button_id: int, message_id: int | None = None, text: str | None = None, link: str | None = None) -> Button:
        async with self.session() as session:
            return await button_repo.update_button(session, button_id=button_id, message_id=message_id, text=text, link=link)

    async def delete_button(self, button_id: int):
        async with self.session() as session:
            return await button_repo.delete_button(session, button_id)

    async def get_message_buttons(self, message_id: int) -> Sequence[Button]:
        async with self.session() as session:
            return await button_repo.get_message_buttons(session, message_id)
