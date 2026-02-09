from typing import Sequence

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, MaybeInaccessibleMessageUnion
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from sqlalchemy.orm import Mapped

from app.bot.core import bot
from app.db.models.group import Group
from app.db.models.group_topic import GroupTopic
from app.db.models.message import Message
from app.schemas.callbacks import AdminCallback, AdminMenuAction, GroupFeature
from app.schemas.group_features import ChannelFeatures, GroupFeatures
from app.services.group import GroupService


async def edit_message_safely(message: MaybeInaccessibleMessageUnion, text: str,
                              reply_markup: InlineKeyboardMarkup | None = None):
    try:
        if reply_markup is not None:
            return await message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            return await message.edit_text(text=text, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            logger.warning(e)
            pass
        else:
            logger.error(e)
    except Exception as e:
        logger.error(f"Failed to edit message {message.message_id}: {e}")


async def delete_messages_safely(chat_id: int, message_ids: Sequence[int] | Sequence[Mapped[int]]):
    for message_id in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.error(f"Failed to delete message {message_id} in chat {chat_id}: {e}")


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


async def build_main_features_keyboard(group_id: int,
                                       features: GroupFeatures | ChannelFeatures) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Make a new announcement ➡️",
                   callback_data=AdminCallback(level=1, action=AdminMenuAction.make_announcement,
                                               group_id=group_id).pack())
    builder.button(text="Manage announcements ➡️",
                   callback_data=AdminCallback(level=1, action=AdminMenuAction.manage_announcements,
                                               group_id=group_id).pack())

    for name, value in features.model_dump().items():
        button_text = name.replace("_", " ").capitalize()
        if name == "greeting_watch":
            button_text = "Greeting Watch ➡️"
            action = AdminMenuAction.open_feature
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
    builder.button(text="Improve with AI 🤖",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.rewrite_announcement_with_ai,
                                               group_id=group_id).pack())
    builder.button(text="⬅️ Back",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.back,
                                               group_id=group_id).pack())
    builder.button(text="Confirm ✅",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.confirm_announcement,
                                               group_id=group_id).pack())
    builder.adjust(1, 2)
    return builder.as_markup()


async def build_confirm_ai_vs_human_announcement_keyboard(group_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="AI version 🤖",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.confirm_ai_announcement,
                                               group_id=group_id).pack())
    builder.button(text="Human version 🌏",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.confirm_announcement,
                                               group_id=group_id).pack())
    builder.button(text="⬅️ Back",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.back,
                                               group_id=group_id).pack())
    builder.adjust(2, 1)
    return builder.as_markup()


async def build_modify_ai_vs_human_announcement_keyboard(group_id: int, announcement_id: int,
                                                         offset: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="AI version 🤖",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.confirm_ai_announcement,
                                               announcement_offset=offset,
                                               announcement_id=announcement_id,
                                               group_id=group_id).pack())
    builder.button(text="Human version 🌏",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.manage_announcements,
                                               announcement_offset=offset,
                                               announcement_id=announcement_id,
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


async def build_announcement_mgmt_message(announcement: Message | None, group_id: int, count: int,
                                          offset: int, can_pin_announcements: bool | None = False) -> tuple[
    str, InlineKeyboardMarkup]:
    builder = InlineKeyboardBuilder()
    if not announcement:
        text = "No announcements yet."
        builder.button(text="⬅️ Back",
                       callback_data=AdminCallback(level=2, action=AdminMenuAction.back,
                                                   group_id=group_id).pack())
        return text, builder.as_markup()
    text = await build_announcement_data(announcement)
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
    builder.button(text="Improve with AI 🤖",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.rewrite_announcement_with_ai,
                                               announcement_offset=offset,
                                               announcement_id=announcement.id).pack())

    builder.button(text="Modify text",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.edit_announcement_text,
                                               announcement_id=announcement.id,
                                               group_id=announcement.group_id).pack())

    builder.button(text="Modify picture" if announcement.picture else "Add picture",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.edit_announcement_picture,
                                               announcement_id=announcement.id,
                                               group_id=announcement.group_id).pack())

    if can_pin_announcements:
        builder.button(text="Un-pin 📌" if announcement.is_pinned else "Pin 📌",
                       callback_data=AdminCallback(level=2, action=AdminMenuAction.confirm_pin,
                                                   announcement_offset=offset,
                                                   announcement_id=announcement.id,
                                                   group_id=group_id
                                                   ).pack())

    builder.button(text="Manage buttons",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.modify_announcement_buttons,
                                               announcement_id=announcement.id, group_id=group_id).pack())

    if announcement.can_be_deleted:
        builder.button(text="Delete 🗑️",
                       callback_data=AdminCallback(level=2, action=AdminMenuAction.delete_announcement,
                                                   announcement_offset=offset,
                                                   announcement_id=announcement.id,
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


async def build_modify_buttons_keyboard(announcement: Message) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for button in announcement.buttons:
        builder.button(text=button.text,
                       callback_data=AdminCallback(level=2, action=AdminMenuAction.edit_announcement_button,
                                                   button_id=button.id))
    builder.button(text="Add button",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.add_announcement_button_name,
                                               group_id=announcement.group_id,
                                               announcement_id=announcement.id).pack())
    builder.button(text="⬅️ Back",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.back,
                                               group_id=announcement.group_id).pack())
    builder.adjust(1)
    return builder.as_markup()


async def build_edit_button_keyboard(button_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Edit text", callback_data=AdminCallback(level=2, action=AdminMenuAction.edit_button_text,
                                                                 button_id=button_id).pack())
    builder.button(text="Edit link", callback_data=AdminCallback(level=2, action=AdminMenuAction.edit_button_link,
                                                                 button_id=button_id).pack())
    builder.button(text="Delete button",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.delete_announcement_button,
                                               button_id=button_id).pack())
    builder.button(text="Cancel", callback_data=AdminCallback(level=2, action=AdminMenuAction.back).pack())
    builder.adjust(1)
    return builder.as_markup()


async def build_announcement_delete_confirmation(announcement: Message, offset: int) -> tuple[
    str, InlineKeyboardMarkup]:
    builder = InlineKeyboardBuilder()
    text = await build_announcement_data(announcement, header="Are you sure you want to delete the announcement?")

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


async def build_announcement_data(announcement: Message, header: str | None = None) -> str:
    creation_date = announcement.created_at.strftime("%d.%m.%Y - %H:%M")
    text = f"{header}\n\n" if header else ""
    text += (f"<code>{creation_date}</code>\n\n"
             f"{announcement.text}\n\n")
    return text


async def build_topics_selection_keyboard(topics: Sequence[GroupTopic], group_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="General", callback_data=AdminCallback(level=2, action=AdminMenuAction.set_topic,
                                                               topic_id=None, group_id=group_id).pack())
    for topic in topics:
        builder.button(text=topic.name, callback_data=AdminCallback(level=2, action=AdminMenuAction.set_topic,
                                                                    topic_id=topic.topic_id,
                                                                    group_id=topic.group_id).pack())
    builder.adjust(1)
    return builder.as_markup()


async def build_yes_no_keyboard(yes_text: str, yes_action: AdminMenuAction, no_text: str, no_action: AdminMenuAction,
                                **callback_kwargs) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    logger.warning(f"Got the kwargs {callback_kwargs}")
    builder.button(text=no_text, callback_data=AdminCallback(level=2, action=no_action, **callback_kwargs).pack())
    builder.button(text=yes_text, callback_data=AdminCallback(level=2, action=yes_action, **callback_kwargs).pack())
    builder.adjust(2)
    return builder.as_markup()


async def build_skip_button(announcement_id: int | Mapped[int], action: AdminMenuAction,
                            button_name: str | None = None, **callback_kwargs) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text=button_name if button_name is not None else "Skip",
                   callback_data=AdminCallback(level=2, action=action,
                                               announcement_id=announcement_id,
                                               **callback_kwargs).pack())
    return builder.as_markup()
