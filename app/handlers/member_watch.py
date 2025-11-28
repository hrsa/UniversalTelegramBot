from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.types import Message, ReactionTypeEmoji

from app.bot.core import bot
from app.db.session import async_session_maker
from app.handlers.admin_interactions import AdminPanel
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
admin_service = AdminService(async_session_maker, gp_service)


@router.message(F.left_chat_member)
async def on_member_leave(message: Message):
    print(message.model_dump_json(indent=4, exclude_none=True))

    print(
        f"User {message.left_chat_member.id} left chat {message.chat.id} "
    )

    if message.left_chat_member.id == bot.id:
        await group_service.leave_group(message.chat.id)
        await gp_service.get_or_create_group_permissions(message.chat.id, role="left")
        return

    try:
        await group_member_service.leave_group(message.chat.id, message.left_chat_member.id)
    except Exception as e:
        print(e)

    if await group_service.feature_is_active(message.chat.id, "report_leaving_members"):
        admins = await user_service.get_group_admins(message.chat.id)
        for admin in admins:
            try:
                if not admin.is_bot:
                    await bot.send_message(admin.id, f"User @{message.left_chat_member.username} left '{message.chat.title}'")
            except Exception as e:
                print(e)
                pass


@router.message(F.new_chat_members)
async def on_member_join(message: Message):
    print(message.model_dump_json(indent=4, exclude_none=True))

    print(
        f"User {message.from_user.id} joined chat {message.chat.id} "
    )

    for member in message.new_chat_members:

        if member.id == bot.id:
            await group_service.get_or_create_group(group_id=message.chat.id, type=message.chat.type,
                                                    title=message.chat.title,
                                                    status="active")
            await group_member_service.get_or_create_member(group_id=message.chat.id, user_id=message.from_user.id,
                                                            first_name=message.from_user.first_name,
                                                            last_name=message.from_user.last_name,
                                                            username=message.from_user.username, role="administrator",
                                                            status="active", is_bot=message.from_user.is_bot)

            my_permissions = await bot.get_chat_member(message.chat.id, bot.id)
            print('got my permissions:')
            print(my_permissions)

            if my_permissions.status == "member":
                await gp_service.get_or_create_group_permissions(message.chat.id, role="member")

            if my_permissions.status == "administrator":
                await gp_service.get_or_create_group_permissions(message.chat.id, role=my_permissions.status, can_be_edited=my_permissions.can_be_edited,
                                                             is_anonymous=my_permissions.is_anonymous, can_manage_chat=my_permissions.can_manage_chat,
                                                             can_delete_messages=my_permissions.can_delete_messages, can_manage_video_chats=my_permissions.can_manage_video_chats,
                                                             can_restrict_members=my_permissions.can_restrict_members, can_promote_members=my_permissions.can_promote_members,
                                                             can_change_info=my_permissions.can_change_info, can_invite_users=my_permissions.can_invite_users,
                                                             can_post_stories=my_permissions.can_post_stories, can_edit_stories=my_permissions.can_edit_stories,
                                                             can_delete_stories=my_permissions.can_delete_stories, can_post_messages=my_permissions.can_post_messages,
                                                             can_edit_messages=my_permissions.can_edit_messages, can_pin_messages=my_permissions.can_pin_messages,
                                                             can_manage_topics=my_permissions.can_manage_topics, can_manage_direct_messages=my_permissions.can_manage_direct_messages,
                                                            custom_title=my_permissions.custom_title, can_manage_voice_chats=my_permissions.can_manage_voice_chats)

            continue

        await group_member_service.get_or_create_member(group_id=message.chat.id, user_id=member.id,
                                                        first_name=member.first_name,
                                                        last_name=member.last_name, username=member.username, is_bot=member.is_bot)

        if await group_service.feature_is_active(message.chat.id, "greeting_watch"):
            greeting_message = await group_service.get_greeting_message(message.chat.id, member.username)
            if greeting_message:
                await bot.send_message(message.chat.id, greeting_message)

        if await group_service.feature_is_active(message.chat.id, "report_new_members"):
            admins = await user_service.get_group_admins(message.chat.id)
            for admin in admins:
                try:
                    if not admin.is_bot:
                        await bot.send_message(admin.id,
                                               f"User @{member.username} joined '{message.chat.title}'")
                except Exception as e:
                    print(e)
                    pass


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

    if member.user.id != bot.id:
        await group_member_service.get_or_create_member(group_id=message.chat.id, user_id=member.user.id, role=member.status)
    else:
        if member.status == "administrator":
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
        else:
            await gp_service.get_or_create_group_permissions(message.chat.id, role=member.status)

# TODO: add method for periodically checking group administrators list