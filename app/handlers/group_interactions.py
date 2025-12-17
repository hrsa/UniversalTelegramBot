from aiogram import Router, F
from aiogram.types import Message

from app.db.session import async_session_maker
from app.services.group import GroupService

router = Router()
group_service = GroupService(async_session_maker)


@router.message(F.new_chat_title)
async def on_new_group_title(message: Message):
    await group_service.update_group_title(message.chat.id, message.new_chat_title)
