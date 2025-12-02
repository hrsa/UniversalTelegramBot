from typing import Sequence

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.db.models.group import Group
from app.handlers.callbacks import AdminCallback, AdminMenuAction, GroupFeature
from app.services.group import GroupService


async def build_group_selection_keyboard(groups: Sequence[Group]) -> InlineKeyboardMarkup:
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
                                 callback_data=AdminCallback(level=1, action=action, feature_name=getattr(GroupFeature, name), group_id=group_id).pack())
        ])

    keyboard.append([InlineKeyboardButton(text="⬅️ Back",
                                          callback_data=AdminCallback(level=1, action=AdminMenuAction.back).pack())])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def build_greeting_watch_keyboard(group_id: int, group_service: GroupService) -> InlineKeyboardMarkup:
    features = await group_service.get_features(group_id)
    keyboard = []

    toggle_text = "Disable greetings" if features.greeting_watch else "Enable greetings"
    keyboard.append([
        InlineKeyboardButton(text=toggle_text, callback_data=AdminCallback(level=2, action=AdminMenuAction.toggle_bool,
                                                                           feature_name=GroupFeature.greeting_watch, group_id=group_id).pack())
    ])

    keyboard.append([InlineKeyboardButton(text="Set Greeting Message",
                                          callback_data=AdminCallback(level=2, action=AdminMenuAction.set_greeting_message,
                                                                      group_id=group_id).pack())
                     ])

    keyboard.append([InlineKeyboardButton(text="Set Reminder Message",
                                          callback_data=AdminCallback(level=2,
                                                                      action=AdminMenuAction.set_reminder_message,
                                                                      group_id=group_id).pack())
                     ])

    keyboard.append([InlineKeyboardButton(text="⬅️ Back", callback_data=AdminCallback(level=2, action=AdminMenuAction.back, group_id=group_id).pack())])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)