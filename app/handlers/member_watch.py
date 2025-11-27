from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.state import State
from aiogram.types import Message, ReactionTypeEmoji

from app.bot.core import bot
from app.config import settings
from app.db.session import async_session_maker
from app.handlers.admin_interactions import AdminPanel
from app.services.admin import AdminService
from app.services.group import GroupService
from app.services.group_member import GroupMemberService
from app.services.user import UserService

router = Router()
group_service = GroupService(async_session_maker)
user_service = UserService(async_session_maker)
group_member_service = GroupMemberService(async_session_maker, group_service, user_service)
admin_service = AdminService(async_session_maker)


@router.message(F.left_chat_member)
async def on_member_leave(message: Message):
    print(message.model_dump_json(indent=4, exclude_none=True))

    print(
        f"User {message.left_chat_member.id} left chat {message.chat.id} "
    )

    if settings.BOT_TELEGRAM_ID & message.left_chat_member.id == settings.BOT_TELEGRAM_ID:
        await group_service.leave_group(message.chat.id)
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

        if member.id == settings.BOT_TELEGRAM_ID:
            await group_service.get_or_create_group(group_id=message.chat.id, type=message.chat.type,
                                                    title=message.chat.title,
                                                    status="active")
            await group_member_service.get_or_create_member(group_id=message.chat.id, user_id=message.from_user.id,
                                                            first_name=message.from_user.first_name,
                                                            last_name=message.from_user.last_name,
                                                            username=message.from_user.username, role="admin",
                                                            status="active", is_bot=message.from_user.is_bot)
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
