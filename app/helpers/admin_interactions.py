from typing import Sequence, get_args

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, MaybeInaccessibleMessageUnion
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from app.bot.core import bot
from app.db.models.group import Group
from app.db.models.message import Message
from app.handlers.admin.callbacks import AdminCallback, AdminMenuAction, GroupFeature
from app.schemas.group_features import ChannelFeatures, GroupFeatures
from app.schemas.literals import RewardType
from app.services.group import GroupService


async def edit_message_safely(message: MaybeInaccessibleMessageUnion, text: str,
                              reply_markup: InlineKeyboardMarkup | None = None):
    try:
        return await message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            logger.warning(e)
            pass
        else:
            logger.error(e)
            raise


async def delete_messages_safely(chat_id: int, message_ids: Sequence[int]):
    for message_id in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.error(f"Failed to delete message {message_id} in chat {chat_id}: {e}")
            continue


async def build_group_selection_keyboard(groups: Sequence[Group]) -> InlineKeyboardMarkup:
    if len(groups) == 0:
        return InlineKeyboardMarkup(inline_keyboard=[])

    builder = InlineKeyboardBuilder()
    for group in groups:
        builder.button(text=group.title,
                       callback_data=AdminCallback(level=0, action=AdminMenuAction.select_group,
                                                   group_id=group.id).pack())

    builder.adjust(1)
    return builder.as_markup()


async def build_main_features_keyboard(group_id: int, features: GroupFeatures | ChannelFeatures,
                                       is_creator: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Make a new announcement ➡️",
                   callback_data=AdminCallback(level=1, action=AdminMenuAction.make_announcement,
                                               group_id=group_id).pack())
    builder.button(text="Manage announcements ➡️",
                   callback_data=AdminCallback(level=1, action=AdminMenuAction.manage_announcements,
                                               group_id=group_id).pack())

    for name, value in features.model_dump().items():
        button_text = name.replace("_", " ").capitalize()
        logger.debug(f"Building keyboard for feature {name}: {value}")
        logger.debug(f"is_creator: {is_creator}")
        if name == "greeting_watch":
            button_text = "Greeting Watch ➡️"
            action = AdminMenuAction.open_feature
        elif name == "allow_payments":
            if is_creator:
                button_text = "Allow Payments"
                button_text += " ✅" if value else " ❌"
                action = AdminMenuAction.toggle_bool
            else:
                continue
        elif isinstance(value, bool):
            button_text += " ✅" if value else " ❌"
            action = AdminMenuAction.toggle_bool
        else:
            button_text += f" ({value})"
            action = AdminMenuAction.set_value

        builder.button(text=button_text,
                       callback_data=AdminCallback(level=1, action=action,
                                                   feature_name=getattr(GroupFeature, name),
                                                   group_id=group_id).pack())

    builder.button(text="⬅️ Back",
                   callback_data=AdminCallback(level=1, action=AdminMenuAction.back).pack())

    builder.adjust(1)
    return builder.as_markup()


async def build_greeting_watch_keyboard(group_id: int, group_service: GroupService) -> InlineKeyboardMarkup:
    features = await group_service.get_features(group_id)
    group = await group_service.get_or_create_group(group_id)

    toggle_text = "Disable greetings" if features.greeting_watch else "Enable greetings"
    greeting_action = "Change greeting message" if group.greeting_message else "Set greeting message"
    reminder_action = "Change reminder message" if group.reminder_message else "Set reminder message"
    builder = InlineKeyboardBuilder()

    if group.greeting_message and group.reminder_message:
        builder.button(text=toggle_text,
                       callback_data=AdminCallback(level=2, action=AdminMenuAction.toggle_bool,
                                                   feature_name=GroupFeature.greeting_watch,
                                                   group_id=group_id).pack())

    builder.button(text=greeting_action,
                   callback_data=AdminCallback(level=2,
                                               action=AdminMenuAction.set_greeting_message,
                                               group_id=group_id).pack())

    builder.button(text=reminder_action,
                   callback_data=AdminCallback(level=2,
                                               action=AdminMenuAction.set_reminder_message,
                                               group_id=group_id).pack())

    builder.button(text="⬅️ Back",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.back,
                                               group_id=group_id).pack())
    builder.adjust(1)
    return builder.as_markup()


async def build_greeting_watch_text(group_id: int, username: str, group_service: GroupService):
    group = await group_service.get_or_create_group(group_id)

    if not group.greeting_message:
        message_text = f"{group.title} has no greeting message yet. Please set it to enable greeting watch!"
    elif not group.reminder_message:
        message_text = f"{group.title} has no reminder message yet. Please set it to enable greeting watch!"
    else:
        message_text = f"{group.title} has the following:\n\n" \
                       "Greeting message:\n" \
                       f"{await group_service.get_greeting_message(group_id=group.id, username=username)} \n\n" \
                       f"Reminder message:\n" \
                       f"{await group_service.get_reminder_message(group_id=group.id, username=username)}"

    return message_text


async def build_confirm_announcement_keyboard(group_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Confirm ✅",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.confirm_announcement,
                                               group_id=group_id).pack())
    builder.button(text="⬅️ Back",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.back,
                                               group_id=group_id).pack())
    builder.adjust(1)
    return builder.as_markup()


async def build_confirm_pin_keyboard(group_id: int, announcement_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text="✅",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.confirm_pin,
                                               group_id=group_id,
                                               announcement_id=announcement_id).pack()),
    builder.button(text="❌",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.back,
                                               group_id=group_id).pack())
    builder.adjust(2)
    return builder.as_markup()


async def build_announcement_mgmt_message(announcements: Sequence[Message], group_id: int, count: int,
                                          offset: int) -> tuple[str, InlineKeyboardMarkup]:
    builder = InlineKeyboardBuilder()

    if not announcements:
        text = "No announcements yet."
        builder.button(text="⬅️ Back",
                       callback_data=AdminCallback(level=2, action=AdminMenuAction.back,
                                                   group_id=group_id).pack())
        return text, builder.as_markup()
    current_announcement = announcements[0]
    creation_date = current_announcement.created_at.strftime("%d.%m.%Y - %H:%M")
    text = f"{creation_date}\n\n{current_announcement.text}"
    button_count = 0
    if offset > 0:
        button_count += 1
        builder.button(text="⬅️", callback_data=AdminCallback(level=2, action=AdminMenuAction.manage_announcements,
                                                              announcement_offset=offset - 1,
                                                              group_id=group_id).pack())
    if offset + 1 < count:
        button_count += 1
        builder.button(text="➡️", callback_data=AdminCallback(level=2, action=AdminMenuAction.manage_announcements,
                                                              announcement_offset=offset + 1,
                                                              group_id=group_id
                                                              ).pack())
    builder.button(text="Un-pin 📌" if current_announcement.is_pinned else "Pin 📌",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.confirm_pin,
                                               announcement_offset=offset,
                                               announcement_id=current_announcement.message_id,
                                               group_id=group_id
                                               ).pack())
    builder.button(text="Un-watch 👀" if current_announcement.is_watched else "Watch 👀",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.confirm_watch,
                                               announcement_offset=offset,
                                               announcement_id=current_announcement.message_id,
                                               group_id=group_id
                                               ).pack())

    builder.button(text="Delete 🗑️",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.delete_announcement,
                                               announcement_offset=offset,
                                               announcement_id=current_announcement.message_id,
                                               group_id=group_id
                                               ).pack())

    builder.button(text="⬅️ Back",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.back,
                                               group_id=group_id).pack())
    if button_count > 1:
        builder.adjust(2, 1)
    else:
        builder.adjust(1)
    return text, builder.as_markup()


async def build_announcement_delete_confirmation(announcement: Message, offset: int) -> tuple[
    str, InlineKeyboardMarkup]:
    builder = InlineKeyboardBuilder()
    creation_date = announcement.created_at.strftime("%d.%m.%Y - %H:%M")
    expiration_date = announcement.payment_expires_at.strftime("%d.%m.%Y") if announcement.payment_expires_at else None
    text = f"Are you sure you want to delete the announcement?\n\n{creation_date}\n\n{announcement.text}\n\nPayment expiration date: {expiration_date if expiration_date else 'N/A'}"

    builder.button(text="⬅️ Back",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.back,
                                               announcement_offset=offset,
                                               announcement_id=announcement.message_id,
                                               group_id=announcement.group_id).pack())

    builder.button(text="Delete 🗑️",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.confirm_delete_announcement,
                                               announcement_offset=offset,
                                               announcement_id=announcement.message_id,
                                               group_id=announcement.group_id
                                               ).pack())
    builder.adjust(2)
    return text, builder.as_markup()


async def build_skip_button(announcement_id: int, group_id: int, action: AdminMenuAction,
                            button_name: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text=button_name if button_name is not None else "Skip",
                   callback_data=AdminCallback(level=2, action=action,
                                               announcement_id=announcement_id,
                                               group_id=group_id).pack())

    return builder.as_markup()


async def build_reward_type_keyboard(announcement_id: int, group_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for reward_type in get_args(RewardType):
        builder.button(text=reward_type.capitalize(),
                       callback_data=AdminCallback(level=2, action=AdminMenuAction.set_reward_type,
                                                   announcement_id=announcement_id, group_id=group_id,
                                                   reward_type=reward_type).pack())

    return builder.as_markup()

async def build_invitation_group_keyboard(groups: Sequence[Group]) -> InlineKeyboardMarkup:
    if len(groups) == 0:
        return InlineKeyboardMarkup(inline_keyboard=[])

    builder = InlineKeyboardBuilder()
    for group in groups:
        builder.button(text=group.title,
                       callback_data=AdminCallback(level=2, action=AdminMenuAction.set_invitation_group,
                                                   group_id=group.id).pack())

    builder.adjust(1)
    return builder.as_markup()
