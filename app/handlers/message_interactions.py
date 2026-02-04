from typing import cast

from aiogram import Router, F
from aiogram.types import Message
from loguru import logger

from app.db.session import async_session_maker
from app.schemas.literals import GroupType
from app.services.group import GroupService
from app.services.group_member import GroupMemberService
from app.services.message import MessageService
from app.services.user import UserService

router = Router()
user_service = UserService(async_session_maker)
group_service = GroupService(async_session_maker)
group_member_service = GroupMemberService(async_session_maker, group_service, user_service)
message_service = MessageService(async_session_maker)


@router.message(F.text)
async def update_group_members_and_group_topics(message: Message):
    group_type = cast(GroupType, message.chat.type) if message.chat.type is not None else None
    if group_type != "private":
        await group_member_service.get_or_create_member(group_id=message.chat.id,
                                                        group_title=message.chat.title,
                                                        group_type=group_type,
                                                        user_id=message.from_user.id,
                                                        first_name=message.from_user.first_name,
                                                        last_name=message.from_user.last_name,
                                                        username=message.from_user.username,
                                                        locale=message.from_user.language_code,
                                                        is_bot=message.from_user.is_bot)

    if message.is_topic_message and message.reply_to_message and message.reply_to_message.forum_topic_created:
        logger.info("Dumping is_topic_message")
        logger.info(message)
        await group_service.get_or_create_topic(group_id=message.chat.id, topic_id=message.message_thread_id, topic_name=message.reply_to_message.forum_topic_created.name)