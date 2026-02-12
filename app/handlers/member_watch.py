from typing import cast

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import Message, ReactionTypeEmoji, User
from loguru import logger

from app.bot.core import bot
from app.db.session import async_session_maker
from app.events.emitter import emit_event
from app.events.schemas import GetGroupAdminsEvent
from app.handlers.admin.admin_interactions import AdminPanel
from app.schemas.literals import GroupType
from app.services.admin import AdminService
from app.services.group import GroupService
from app.services.group_member import GroupMemberService
from app.services.group_permission import GroupPermissionService
from app.services.user import UserService

router = Router()
group_service = GroupService(async_session_maker)
user_service = UserService(async_session_maker)
group_member_service = GroupMemberService(async_session_maker, group_service, user_service)
gp_service = GroupPermissionService(async_session_maker)
admin_service = AdminService(async_session_maker, group_service, gp_service)


def pretty_print_user(user: User) -> str:
    result = ""
    if user.is_bot:
        result += "<b><u>THIS PERSON IS A BOT!</u></b>\n\n"

    full_name = " ".join(part for part in (user.first_name, user.last_name) if part)
    if full_name:
        result += f"{full_name} (@{user.username})"
    else:
        result += f"@{user.username}"
    return result


@router.chat_member()
async def on_chat_member_update(message: Message):
    group_type = cast(GroupType | None, message.chat.type)
    group = await group_service.update_group(group_id=message.chat.id, group_type=group_type,
                                             title=message.chat.title,
                                             status="active")
    member = message.new_chat_member
    member_joined = member.status != "kicked" and member.status != "left"
    await group_member_service.get_or_create_member(group_id=group.id, group_type=group_type,
                                                    group_title=message.chat.title,
                                                    user_id=member.user.id,
                                                    first_name=member.user.first_name,
                                                    last_name=member.user.last_name, username=member.user.username,
                                                    is_bot=member.user.is_bot, locale=member.user.language_code,
                                                    status="left" if member.status == "kicked" or member.status == "left" else "active",
                                                    role=member.status)

    if member_joined:
        if group.type == "supergroup" and await group_service.feature_is_active(group.id, "greeting_watch"):
            greeting_message = await group_service.get_greeting_message(group.id, member.user.username)
            if greeting_message:
                await bot.send_message(message.chat.id, greeting_message)

        if await group_service.feature_is_active(group.id, "report_new_members"):
            await user_service.notify_admins(f"🙂\n\n{pretty_print_user(member.user)} joined '{group.title}'", group.id)
    else:
        if await group_service.feature_is_active(group.id, "report_leaving_members"):
            await user_service.notify_admins(f"😢\n\n{pretty_print_user(member.user)} left '{group.title}'", group.id)


@router.message(F.left_chat_participant)
async def left_chat_participant_message(message: Message):
    if message.left_chat_member.id == bot.id:
        await group_service.leave_group(message.chat.id)
    else:
        group = await group_service.get_group(message.chat.id)
        if await group_service.feature_is_active(message.chat.id, "report_leaving_members"):
            await user_service.notify_admins(f"😢\n\n{pretty_print_user(message.left_chat_member)} left '{group.title}'",
                                             group.id)


@router.chat_join_request()
async def inform_admins_about_join_request(message: Message):
    group = await group_service.get_group(message.chat.id)
    if not group:
        logger.error("Group not found")
        return
    await user_service.notify_admins(
        f"❗❗❗\n\n{pretty_print_user(message.from_user)} has requested to join '{group.title}'",
        group.id)


@router.message(F.text.contains("#"), ~StateFilter(AdminPanel))
async def react_to_greeting(message: Message):
    if not await group_service.feature_is_active(message.chat.id, "greeting_watch"):
        return

    greeting_processed = await group_member_service.greeting_processed(message.chat.id, message.from_user.id, message)

    if greeting_processed:
        await bot.set_message_reaction(message.chat.id, message.message_id, [ReactionTypeEmoji(emoji="❤")], is_big=True)
    # else:
    #     await bot.set_message_reaction(message.chat.id, message.message_id, [ReactionTypeEmoji(emoji="👎")])


@router.my_chat_member()
async def on_member_status_change(message: Message):
    member = message.new_chat_member
    group_type = cast(GroupType | None, message.chat.type)
    group = await group_service.update_group(group_id=message.chat.id, group_type=group_type,
                                             title=message.chat.title,
                                             status="active")

    if (member.status == "administrator") and member.user.id == bot.id:
        await emit_event("get_group_admins", GetGroupAdminsEvent(group_id=group.id))
        await gp_service.get_or_create_group_permissions(message.chat.id, role=member.status,
                                                         can_be_edited=member.can_be_edited,
                                                         is_anonymous=member.is_anonymous,
                                                         can_manage_chat=member.can_manage_chat,
                                                         can_delete_messages=member.can_delete_messages,
                                                         can_manage_video_chats=member.can_manage_video_chats,
                                                         can_restrict_members=member.can_restrict_members,
                                                         can_promote_members=member.can_promote_members,
                                                         can_change_info=member.can_change_info,
                                                         can_invite_users=member.can_invite_users,
                                                         can_post_stories=member.can_post_stories,
                                                         can_edit_stories=member.can_edit_stories,
                                                         can_delete_stories=member.can_delete_stories,
                                                         can_post_messages=member.can_post_messages,
                                                         can_edit_messages=member.can_edit_messages,
                                                         can_pin_messages=member.can_pin_messages,
                                                         can_manage_topics=member.can_manage_topics,
                                                         can_manage_direct_messages=member.can_manage_direct_messages,
                                                         custom_title=member.custom_title,
                                                         can_manage_voice_chats=member.can_manage_voice_chats)
    elif member.status == "left":
        await group_service.leave_group(message.chat.id)
        await gp_service.get_or_create_group_permissions(message.chat.id, role="left")
    else:
        await gp_service.get_or_create_group_permissions(message.chat.id, role=member.status)
