from typing import Sequence

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger

from app.bot.core import bot
from app.db.models.message import Message
from app.db.session import async_session_maker
from app.handlers.callbacks import AdminCallback, AdminMenuAction, GroupFeature
from app.helpers.admin_interactions import build_main_features_keyboard, build_greeting_watch_keyboard, \
    build_group_selection_keyboard, edit_message_safely, build_greeting_watch_text, build_confirm_announcement_keyboard, \
    build_confirm_pin_keyboard, build_announcement_mgmt_message, build_announcement_delete_confirmation
from app.services.admin import AdminService
from app.services.group import GroupService
from app.services.group_permission import GroupPermissionService
from app.services.message import MessageService

router = Router()
group_permission_service = GroupPermissionService(async_session_maker)
admin_service = AdminService(async_session_maker, group_permission_service)
group_service = GroupService(async_session_maker)
message_service = MessageService(async_session_maker)


class AdminPanel(StatesGroup):
    choosing_group = State()
    managing_features = State()
    managing_greeting_watch = State()
    setting_greeting_message = State()
    setting_reminder_message = State()
    creating_announcement = State()
    confirming_announcement = State()
    confirming_pin = State()
    managing_announcements = State()
    confirming_delete_announcement = State()


@router.message(Command("manage"))
async def start_command(message: Message, state: FSMContext):
    if message.chat.type != "private":
        await message.answer("This command is available only in private chats.")
        return

    my_groups = await admin_service.get_my_groups(message.from_user.id)
    if not my_groups:
        await message.answer("You are not an admin in any groups that I am in.")
        return

    welcome_text = (
        f"Hello, my dear tester {message.from_user.full_name}!\n\n"
        f"Please select a group from the list below:"
    )

    keyboard = await build_group_selection_keyboard(my_groups)

    await bot.send_message(message.from_user.id, welcome_text, reply_markup=keyboard)

    await state.set_state(AdminPanel.choosing_group)


@router.callback_query(AdminPanel.choosing_group, AdminCallback.filter(F.action == AdminMenuAction.select_group))
async def process_group_selection(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    group_id = callback_data.group_id
    group = await group_service.get_or_create_group(group_id)

    keyboard = await build_main_features_keyboard(group_id, group_service)

    await edit_message_safely(message=callback.message,
                              text=f"Selected group: {group.title}. What do you want to do with it?",
                              reply_markup=keyboard)
    await state.set_state(AdminPanel.managing_features)


@router.callback_query(AdminPanel.managing_features, AdminCallback.filter(
    (F.feature_name == GroupFeature.greeting_watch) & (F.action == AdminMenuAction.open_feature)))
async def open_greeting_watch(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    group = await group_service.get_or_create_group(callback_data.group_id)
    keyboard = await build_greeting_watch_keyboard(group.id, group_service)

    message_text = await build_greeting_watch_text(group.id, callback.from_user.username, group_service)

    await edit_message_safely(message=callback.message, text=message_text, reply_markup=keyboard)
    await state.set_state(AdminPanel.managing_greeting_watch)


@router.callback_query(AdminPanel.managing_features,
                       AdminCallback.filter(F.action == AdminMenuAction.make_announcement))
async def make_announcement(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    group = await group_service.get_or_create_group(callback_data.group_id)
    await state.update_data(group_id=callback_data.group_id)
    await state.update_data(message_id=callback.message.message_id)
    await edit_message_safely(message=callback.message,
                              text=f"Please enter the announcement message for {group.title}.")
    await state.set_state(AdminPanel.creating_announcement)


@router.message(AdminPanel.creating_announcement)
async def show_confirmation_dialogue(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    message_id = await state.get_value("message_id")
    await state.update_data(announcement_text=message.text)
    try:
        await bot.delete_message(message.chat.id, message.message_id)
        await bot.delete_message(message.chat.id, message_id)
    except Exception as e:
        logger.error(e)

    keyboard = await build_confirm_announcement_keyboard(group_id)

    confirmation_text = f"Here is the announcement i'll send:\n\n{message.text}"

    await bot.send_message(message.chat.id, text=confirmation_text, reply_markup=keyboard)
    await state.set_state(AdminPanel.confirming_announcement)


@router.callback_query(AdminPanel.confirming_announcement,
                       AdminCallback.filter((F.action == AdminMenuAction.confirm_announcement) & F.level == 2))
async def send_announcement(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    group_id = await state.get_value("group_id")
    announcement_text = await state.get_value("announcement_text")
    announcement = await bot.send_message(chat_id=group_id, text=announcement_text)
    saved_announcement = await message_service.create_message(group_id=group_id, message_id=announcement.message_id,
                                                              text=announcement_text, is_watched=True, is_pinned=False)
    keyboard = await build_confirm_pin_keyboard(group_id=group_id, announcement_id=saved_announcement.message_id)
    await edit_message_safely(message=callback.message,
                              text=f"Announcement sent successfully!\nDo you want me to pin it?", reply_markup=keyboard)
    await state.set_state(AdminPanel.confirming_pin)


@router.callback_query(AdminPanel.confirming_pin,
                       AdminCallback.filter((F.action == AdminMenuAction.confirm_pin) & F.level == 2))
async def pin_announcement(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await bot.pin_chat_message(chat_id=callback_data.group_id, message_id=callback_data.announcement_id)
    await message_service.pin_message(group_id=callback_data.group_id, message_id=callback_data.announcement_id)
    await callback.answer("Pinned successfully!")

    await state.set_state(AdminPanel.managing_features)
    await process_group_selection(callback, callback_data, state)


@router.callback_query(AdminPanel.managing_features,
                       AdminCallback.filter(F.action == AdminMenuAction.delete_announcement))
async def confirm_announcement_deletion(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    announcement = await message_service.get_message(group_id=callback_data.group_id,
                                                     message_id=callback_data.announcement_id)
    text, keyboard = await build_announcement_delete_confirmation(announcement, callback_data.announcement_offset)
    await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)

@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.confirm_delete_announcement))
async def delete_announcement(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await bot.delete_message(chat_id=callback_data.group_id, message_id=callback_data.announcement_id)
    await message_service.delete_message(group_id=callback_data.group_id, message_id=callback_data.announcement_id)
    await callback.answer("Announcement deleted successfully!")
    await manage_announcements(callback, callback_data, state)


@router.callback_query(AdminPanel.managing_features,
                       AdminCallback.filter(F.action == AdminMenuAction.manage_announcements))
async def manage_announcements(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    offset = callback_data.announcement_offset if callback_data.announcement_offset is not None else 0
    limit = 1
    announcements, count = await group_service.get_group_announcements(callback_data.group_id, offset, limit)
    text, keyboard = await build_announcement_mgmt_message(announcements, callback_data.group_id, count, offset)
    await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)


@router.callback_query(AdminPanel.managing_features, AdminCallback.filter((F.action == AdminMenuAction.confirm_pin) |
                                                                          (F.action == AdminMenuAction.confirm_watch)))
async def toggle_pin_or_watch(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    announcement = await message_service.get_message(group_id=callback_data.group_id,
                                                     message_id=callback_data.announcement_id)
    if announcement is None:
        logger.warning(f"Announcement {callback_data.announcement_id} not found in database.")
        return

    if callback_data.action == AdminMenuAction.confirm_pin:
        if announcement.is_pinned:
            await bot.unpin_chat_message(chat_id=callback_data.group_id, message_id=callback_data.announcement_id)
            await message_service.unpin_message(group_id=callback_data.group_id,
                                                message_id=callback_data.announcement_id)
            await callback.answer("Un-pinned successfully!")
        else:
            await bot.pin_chat_message(chat_id=callback_data.group_id, message_id=callback_data.announcement_id)
            await message_service.pin_message(group_id=callback_data.group_id, message_id=callback_data.announcement_id)
            await callback.answer("Pinned successfully!")
    if callback_data.action == AdminMenuAction.confirm_watch:
        if announcement.is_watched:
            await message_service.unwatch_message(group_id=callback_data.group_id,
                                                  message_id=callback_data.announcement_id)
            await callback.answer("Un-watched successfully!")
        else:
            await message_service.watch_message(group_id=callback_data.group_id,
                                                message_id=callback_data.announcement_id)
            await callback.answer("Watched successfully!")

    await manage_announcements(callback, callback_data, state)


@router.callback_query(AdminPanel.managing_greeting_watch,
                       AdminCallback.filter(F.action == AdminMenuAction.set_greeting_message))
async def request_new_greeting_message(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await edit_message_safely(message=callback.message,
                              text="Please enter a new greeting message. Don't forget to include a hashtag like #bio or #greeting. Add %USERNAME% if you want to include the username in the message.")
    await state.update_data(group_id=callback_data.group_id)
    await state.update_data(message_id=callback.message.message_id)
    await state.set_state(AdminPanel.setting_greeting_message)


@router.message(AdminPanel.setting_greeting_message)
async def set_new_greeting_message(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    message_id = await state.get_value("message_id")
    try:
        group = await admin_service.set_group_greeting(group_id, message)
    except ValueError as e:
        await bot.send_message(message.chat.id, e.args[0])
        group = await group_service.get_or_create_group(group_id)
    try:
        await bot.delete_message(message.chat.id, message.message_id)
        await bot.delete_message(message.chat.id, message_id)
    except Exception as e:
        logger.error(e)
    keyboard = await build_greeting_watch_keyboard(group_id, group_service)

    message_text = await build_greeting_watch_text(group_id, message.from_user.username, group_service)

    await bot.send_message(message.chat.id, message_text, reply_markup=keyboard)
    await state.set_state(AdminPanel.managing_greeting_watch)


@router.callback_query(AdminPanel.managing_greeting_watch,
                       AdminCallback.filter(F.action == AdminMenuAction.set_reminder_message))
async def request_new_reminder_message(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await edit_message_safely(message=callback.message,
                              text="Please enter a new reminder message that will be followed by the repeated greeting. Add %USERNAME% if you want to include the username in the message.")
    await state.update_data(group_id=callback_data.group_id)
    await state.update_data(message_id=callback.message.message_id)
    await state.set_state(AdminPanel.setting_reminder_message)


@router.message(AdminPanel.setting_reminder_message)
async def set_new_reminder_message(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    message_id = await state.get_value("message_id")
    try:
        group = await admin_service.set_group_reminder(group_id, message.text)
    except ValueError as e:
        await bot.send_message(message.chat.id, e.args[0])
        group = await group_service.get_or_create_group(group_id)
    try:
        await bot.delete_message(message.chat.id, message.message_id)
        await bot.delete_message(message.chat.id, message_id)
    except Exception as e:
        logger.error(e)
    keyboard = await build_greeting_watch_keyboard(group_id, group_service)

    message_text = await build_greeting_watch_text(group_id, message.from_user.username, group_service)

    await bot.send_message(message.chat.id, message_text, reply_markup=keyboard)
    await state.set_state(AdminPanel.managing_greeting_watch)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.toggle_bool))
async def toggle_feature(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    feature_name = callback_data.feature_name.name
    group_id = callback_data.group_id
    group = await group_service.get_or_create_group(group_id)
    try:
        await admin_service.toggle_feature(group_id, feature_name)
    except PermissionError as e:
        if e.args[0] == "greeting_watch":
            keyboard = await build_greeting_watch_keyboard(group_id, group_service)
            await edit_message_safely(message=callback.message, text=e.args[1], reply_markup=keyboard)
        return

    await callback.answer(
        f"Feature {feature_name} changed."
    )

    if await state.get_state() == AdminPanel.managing_features:
        message_text = f"{feature_name} was updated successfully!\n\n" \
                       f"Selected group: {group.title}. What do you want to do with it?"
        keyboard = await build_main_features_keyboard(group_id, group_service)
        await edit_message_safely(message=callback.message, text=message_text, reply_markup=keyboard)

    elif await state.get_state() == AdminPanel.managing_greeting_watch:
        message_text = f"{feature_name} was updated successfully!\n\n" \
                       f"{group.title} has the following greeting message:\n\n" \
                       f"{group.greeting_message}"
        keyboard = await build_greeting_watch_keyboard(group_id, group_service)
        await edit_message_safely(message=callback.message, text=message_text, reply_markup=keyboard)

    else:
        await edit_message_safely(message=callback.message, text="Unknown state.")


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.back))
async def go_back(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    if callback_data.level == 2:
        await state.set_state(AdminPanel.managing_features)
        await process_group_selection(callback, callback_data, state)
    elif callback_data.level == 1:
        await state.set_state(AdminPanel.choosing_group)
        my_groups = await admin_service.get_my_groups(callback.from_user.id)

        welcome_text = (
            f"Hello, my dear {callback.from_user.full_name}!\n\n"
            f"Please select a group from the list below:"
        )

        keyboard = await build_group_selection_keyboard(my_groups)

        await edit_message_safely(message=callback.message, text=welcome_text, reply_markup=keyboard)
    else:
        await edit_message_safely(message=callback.message, text="Back to main menu.")


@router.message(Command('quit'))
async def quit_admin_interface(message: Message, state: FSMContext):
    await message.answer("Bye!")
    await state.clear()


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.quit))
async def quit_admin_interface_from_callback(callback: CallbackQuery, state: FSMContext):
    await quit_admin_interface(callback.message, state)
