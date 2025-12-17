from typing import Sequence

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, MaybeInaccessibleMessageUnion
from loguru import logger

from app.db.models.group import Group
from app.handlers.callbacks import AdminCallback, AdminMenuAction, GroupFeature
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


async def build_group_selection_keyboard(groups: Sequence[Group]) -> InlineKeyboardMarkup:
    if len(groups) == 0:
        return InlineKeyboardMarkup(inline_keyboard=[])

    keyboard = []
    for group in groups:
        button = InlineKeyboardButton(text=group.title,
                                      callback_data=AdminCallback(level=0, action=AdminMenuAction.select_group,
                                                                  group_id=group.id).pack())
        keyboard.append([button])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def build_main_features_keyboard(group_id: int, group_service: GroupService) -> InlineKeyboardMarkup:
    features = await group_service.get_features(group_id)
    keyboard = []
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

        keyboard.append([
            InlineKeyboardButton(text=button_text,
                                 callback_data=AdminCallback(level=1, action=action,
                                                             feature_name=getattr(GroupFeature, name),
                                                             group_id=group_id).pack())
        ])

    keyboard.append([InlineKeyboardButton(text="⬅️ Back",
                                          callback_data=AdminCallback(level=1, action=AdminMenuAction.back).pack())])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def build_greeting_watch_keyboard(group_id: int, group_service: GroupService) -> InlineKeyboardMarkup:
    features = await group_service.get_features(group_id)
    group = await group_service.get_or_create_group(group_id)
    keyboard = []

    toggle_text = "Disable greetings" if features.greeting_watch else "Enable greetings"
    greeting_action = "Change greeting message" if group.greeting_message else "Set greeting message"
    reminder_action = "Change reminder message" if group.reminder_message else "Set reminder message"

    if group.greeting_message and group.reminder_message:
        keyboard.append([
            InlineKeyboardButton(text=toggle_text,
                                 callback_data=AdminCallback(level=2, action=AdminMenuAction.toggle_bool,
                                                             feature_name=GroupFeature.greeting_watch,
                                                             group_id=group_id).pack())
        ])

    keyboard.append([InlineKeyboardButton(text=greeting_action,
                                          callback_data=AdminCallback(level=2,
                                                                      action=AdminMenuAction.set_greeting_message,
                                                                      group_id=group_id).pack())
                     ])

    keyboard.append([InlineKeyboardButton(text=reminder_action,
                                          callback_data=AdminCallback(level=2,
                                                                      action=AdminMenuAction.set_reminder_message,
                                                                      group_id=group_id).pack())
                     ])

    keyboard.append([InlineKeyboardButton(text="⬅️ Back",
                                          callback_data=AdminCallback(level=2, action=AdminMenuAction.back,
                                                                      group_id=group_id).pack())])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


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
