from typing import cast

from aiogram import Router, F
from aiogram.types import Message

from app.db.session import async_session_maker
from app.events.emitter import emit_event
from app.events.schemas import GetGroupAdminsEvent
from app.schemas.literals import GroupType
from app.services.group import GroupService
from app.services.group_permission import GroupPermissionService

router = Router()
group_service = GroupService(async_session_maker)
gp_service = GroupPermissionService(async_session_maker)


@router.message(F.new_chat_title)
async def on_new_group_title(message: Message):
    await group_service.update_group_title(message.chat.id, message.new_chat_title)


@router.message(F.group_chat_created)
async def on_group_created(message: Message):
    group_type = cast(GroupType | None, message.chat.type)
    group = await group_service.update_group(group_id=message.chat.id, group_type=group_type,
                                                    title=message.chat.title,
                                                    status="active")

    if message.chat.all_members_are_administrators:
        await emit_event("get_group_admins", GetGroupAdminsEvent(group_id=group.id))
        await gp_service.get_or_create_group_permissions(message.chat.id, role="member",
                                                         can_be_edited=True,
                                                         is_anonymous=False,
                                                         can_manage_chat=True,
                                                         can_delete_messages=True,
                                                         can_manage_video_chats=False,
                                                         can_restrict_members=False,
                                                         can_promote_members=False,
                                                         can_change_info=False,
                                                         can_invite_users=False,
                                                         can_post_stories=False,
                                                         can_edit_stories=True,
                                                         can_delete_stories=True,
                                                         can_post_messages=True,
                                                         can_edit_messages=True,
                                                         can_pin_messages=False,
                                                         can_manage_topics=False,
                                                         can_manage_direct_messages=False,
                                                         custom_title=None,
                                                         can_manage_voice_chats=False)


@router.message(F.migrate_from_chat_id)
async def migrate_group(message: Message):
    new_group = await group_service.get_group(message.chat.id)

    if new_group is None:
        group_type = cast(GroupType | None, message.chat.type)
        await group_service.update_group(group_id=message.migrate_from_chat_id, new_group_id=message.chat.id,
                                     group_type=group_type, title=message.chat.title, status="active")
    else:
        await group_service.delete_group(message.migrate_from_chat_id)
