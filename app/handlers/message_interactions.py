from typing import cast

from aiogram import Router, F
from aiogram.types import MessageReactionUpdated, ReactionTypeEmoji, ReactionTypeUnion, CallbackQuery, Message
from loguru import logger

from app.db.session import async_session_maker
from app.schemas.callbacks import AnnouncementCallback, AnnouncementAction
from app.schemas.literals import GroupType
from app.services.group import GroupService
from app.services.group_member import GroupMemberService
from app.services.message import MessageService
from app.services.payment import PaymentService
from app.services.user import notify_user, UserService

router = Router()
user_service = UserService(async_session_maker)
group_service = GroupService(async_session_maker)
group_member_service = GroupMemberService(async_session_maker, group_service, user_service)
message_service = MessageService(async_session_maker)
payment_service = PaymentService(async_session_maker, message_service)


@router.callback_query(AnnouncementCallback.filter(F.action == AnnouncementAction.join))
async def on_join_announcement(callback: CallbackQuery, callback_data: AnnouncementCallback):
    group_type = cast(GroupType, callback.message.chat.type) if callback.message.chat.type is not None else None

    await group_member_service.get_or_create_member(group_id=callback.message.chat.id,
                                                    group_title=callback.message.chat.title,
                                                    group_type=group_type,
                                                    user_id=callback.from_user.id,
                                                    first_name=callback.from_user.first_name,
                                                    last_name=callback.from_user.last_name,
                                                    username=callback.from_user.username,
                                                    is_bot=callback.from_user.is_bot)

    reply_text = (f"Hi {callback.from_user.first_name if callback.from_user.first_name is not None else f'@{callback.from_user.username}'},\n"
                  f"I am the administrator of <b>'{callback.message.chat.title}'</b>.\n\n")

    try:
        await callback.answer("Check your private messages! 👀")
    except Exception as e:
        logger.exception(f"Failed to answer callback: {e}")

    announcement = await message_service.get_message(announcement_id=callback_data.announcement_id)
    if not announcement:
        logger.warning(f"Announcement {callback_data.announcement_id} not found")
        return None

    if announcement.is_expired:
        reply_text += f"Sorry, <b>'{callback_data.event_name}'</b> has already ended. You can't join it anymore."
        await notify_user(user_id=callback.from_user.id,
                          message=reply_text)
        return await message_service.remove_button_from_announcement(announcement.group_id, announcement.message_id)

    payment = await payment_service.get_payment(user_id=callback.from_user.id, announcement_id=announcement.id)
    if payment and payment.status == "paid":
        reply_text = f"You've already joined and paid for <b>'{callback_data.event_name}'</b>!"
        return await notify_user(user_id=callback.from_user.id, message=reply_text)

    is_full, pending = await payment_service.verify_event_capacity(announcement.id)
    if is_full and pending == 0:
        reply_text += f"Sorry, <b>'{callback_data.event_name}'</b> is full and has no pending participants! Please join the next one."
        return await notify_user(user_id=callback.from_user.id, message=reply_text)
    if is_full and pending > 0:
        await payment_service.create_payment(group_id=announcement.group_id,
                                                       message_id=announcement.message_id,
                                                       user_id=callback.from_user.id, status="waiting")
        reply_text += (f"Sorry, <b>'{callback_data.event_name}'</b> is currently full.\n\nThere are {pending} participants who haven't paid yet."
                       f"If they don't pay in the next 15 minutes, i'll give their place to you!")
        return await notify_user(user_id=callback.from_user.id,
                                 message=reply_text)


    payment = await payment_service.create_payment(group_id=announcement.group_id,
                                                       message_id=announcement.message_id,
                                                       user_id=callback.from_user.id, status="pending")
    reply_text += (f"Thank you for joining {callback_data.event_name}!\n\n"
                   f"Here is your payment link: {payment.url}\n\n"
                   f"Please remember, this link is valid <b><u>only for 15 minutes</u></b>!")
    return await notify_user(user_id=callback.from_user.id,
                             message=reply_text)


@router.message(F.text)
async def add_group_member_if_necessary(message: Message):
    group_type = cast(GroupType, message.chat.type) if message.chat.type is not None else None

    await group_member_service.get_or_create_member(group_id=message.chat.id,
                                                    group_title=message.chat.title,
                                                    group_type=group_type,
                                                    user_id=message.from_user.id,
                                                    first_name=message.from_user.first_name,
                                                    last_name=message.from_user.last_name,
                                                    username=message.from_user.username,
                                                    is_bot=message.from_user.is_bot)