from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.db.models.message_button import Button


async def get_button(session: AsyncSession, button_id: int) -> Button | None:
    stmt = (select(Button)
            .options(selectinload(Button.message))
            .where(Button.id == button_id))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_button(
        session: AsyncSession,
        message_id: int,
        text: str,
        link: str,
) -> Button:
    button = Button(
        message_id=message_id,
        text=text,
        link=link,
    )
    session.add(button)
    await session.commit()

    await session.refresh(button)
    return button


async def update_button(session: AsyncSession,
                        button_id: int,
                        message_id: int | None,
                        text: str | None,
                        link: str | None,
                        ):
    button = await get_button(session=session, button_id=button_id)
    if button is None:
        raise ValueError(f"Button {button_id} not found")
    button.message_id = message_id if message_id is not None else button.message_id
    button.text = text if text is not None else button.text
    button.link = link if link is not None else button.link
    await session.commit()
    await session.refresh(button)
    return button


async def delete_button(session: AsyncSession, button_id: int):
    button = await get_button(session=session, button_id=button_id)
    if button:
        await session.delete(button)
        await session.commit()


async def get_message_buttons(session: AsyncSession, message_id: int) -> Sequence[Button]:
    stmt = (select(Button)
            .where(Button.message_id == message_id)
            .order_by(Button.id.asc()))

    result = await session.execute(stmt)
    return result.scalars().all()
