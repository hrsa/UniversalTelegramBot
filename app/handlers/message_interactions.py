from aiogram import Router, F
from aiogram.types import MessageReactionUpdated, ReactionTypeEmoji, ReactionTypeUnion, CallbackQuery
from loguru import logger

from app.db.session import async_session_maker
from app.handlers.admin.callbacks import AnnouncementCallback, AnnouncementAction
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


def _reaction_to_str(r: ReactionTypeUnion) -> str:
    """
    Convert aiogram reaction union into a stable printable/comparable string.
    """
    if isinstance(r, ReactionTypeEmoji):
        return f"emoji:{r.emoji}"
    # Covers custom_emoji / paid / future types without crashing
    # (model_dump exists on aiogram's pydantic models)
    data = r.model_dump(exclude_none=True)
    r_type = data.get("type", "unknown")
    return f"{r_type}:{data}"


@router.callback_query(AnnouncementCallback.filter(F.action == AnnouncementAction.join))
async def on_join_announcement(callback: CallbackQuery, callback_data: AnnouncementCallback):
    await group_member_service.get_or_create_member(group_id=callback.message.chat.id, user_id=callback.from_user.id,
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
        reply_text += "Sorry, this event is in the past. You can't join it anymore."
        await notify_user(user_id=callback.from_user.id,
                          message=reply_text)
        return await message_service.remove_button_from_announcement(announcement.group_id, announcement.message_id)

    payment = await payment_service.get_payment(user_id=callback.from_user.id, announcement_id=announcement.id)
    if payment and payment.status == "paid":
        reply_text = "You've already paid for this event!"
        return await notify_user(user_id=callback.from_user.id, message=reply_text)

    is_full, pending = await payment_service.verify_event_capacity(announcement.id)
    if is_full and pending == 0:
        reply_text += "Sorry, this event is full and has no pending participants! Please join the next one."
        return await notify_user(user_id=callback.from_user.id, message=reply_text)
    if is_full and pending > 0:
        payment = await payment_service.create_payment(group_id=announcement.group_id,
                                                       message_id=announcement.message_id,
                                                       user_id=callback.from_user.id, status="waiting")
        reply_text += (f"Sorry, this event is currently full.\n\nThere are {pending} participants who haven't paid yet."
                       f"If they don't pay in the next 15 minutes, i'll give their place to you!")
        return await notify_user(user_id=callback.from_user.id,
                                 message=reply_text)
    if not payment:
        payment = await payment_service.create_payment(group_id=announcement.group_id,
                                                       message_id=announcement.message_id,
                                                       user_id=callback.from_user.id, status="pending")
    reply_text += (f"Thank you for joining {callback_data.event_name}!\n\n"
                   f"Here is your payment link: {payment.url}\n\n"
                   f"Please remember, this link is valid <b><u>only for 15 minutes</u></b>!")
    return await notify_user(user_id=callback.from_user.id,
                             message=reply_text)


@router.message_reaction()
async def watch_reactions(event: MessageReactionUpdated):
    username = getattr(event.user, "username", None) or f"id:{event.user.id}"

    old_list: list[ReactionTypeUnion] = list(event.old_reaction or [])
    new_list: list[ReactionTypeUnion] = list(event.new_reaction or [])

    old_set = {_reaction_to_str(r) for r in old_list}
    new_set = {_reaction_to_str(r) for r in new_list}

    added = sorted(new_set - old_set)
    removed = sorted(old_set - new_set)
    kept = sorted(new_set & old_set)

    logger.info(
        "REACTION_UPDATE chat_id={} message_id={} by={}",
        event.chat.id,
        event.message_id,
        username,
    )

    announcement = await message_service.get_message(group_id=event.chat.id, message_id=event.message_id)
    if announcement and announcement.is_watched:
        logger.info("Message is watched, Nice!!")

    logger.info("OLD reactions: {}", sorted(old_set) if old_set else "∅")
    logger.info("NEW reactions: {}", sorted(new_set) if new_set else "∅")

    if added:
        logger.info("ADDED reactions: {}", added)
    if removed:
        logger.info("REMOVED reactions: {}", removed)
    if kept:
        logger.debug("KEPT reactions: {}", kept)
