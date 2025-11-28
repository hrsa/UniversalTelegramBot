from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, \
    CallbackQuery

from app.bot.core import bot
from app.db.session import async_session_maker
from app.handlers.callbacks import AdminCallback, AdminMenuAction, GroupFeature
from app.helpers.admin_interactions import build_main_features_keyboard, build_greeting_watch_keyboard, \
    build_group_selection_keyboard
from app.services.admin import AdminService
from app.services.group import GroupService
from app.services.group_permission import GroupPermissionService

router = Router()
group_permission_service = GroupPermissionService(async_session_maker)
admin_service = AdminService(async_session_maker, group_permission_service)
group_service = GroupService(async_session_maker)


class AdminPanel(StatesGroup):
    choosing_group = State()
    managing_features = State()
    managing_greeting_watch = State()
    setting_greeting_message = State()


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
    # await state.update_data(message_id=message.message_id, selected_group_id=None)

    keyboard = await build_group_selection_keyboard(my_groups)

    await bot.send_message(message.from_user.id, welcome_text, reply_markup=keyboard)

    await state.set_state(AdminPanel.choosing_group)


@router.callback_query(AdminPanel.choosing_group, AdminCallback.filter(F.action == AdminMenuAction.select_group))
async def process_group_selection(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    group_id = callback_data.group_id
    group = await group_service.get_or_create_group(group_id)

    keyboard = await build_main_features_keyboard(group_id, group_service)

    await callback.message.edit_text(text=f"Selected group: {group.title}. What do you want to do with it?",
                                     reply_markup=keyboard)
    await state.set_state(AdminPanel.managing_features)


@router.callback_query(AdminPanel.managing_features, AdminCallback.filter(
    (F.feature_name == GroupFeature.greeting_watch) & (F.action == AdminMenuAction.open_feature)))
async def open_greeting_watch(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    group = await group_service.get_or_create_group(callback_data.group_id)
    keyboard = await build_greeting_watch_keyboard(group.id, group_service)

    message_text = f"{group.title} has the following greeting message:\n\n" \
                   f"{group.greeting_message}"

    await callback.message.edit_text(text=message_text, reply_markup=keyboard)
    await state.set_state(AdminPanel.managing_greeting_watch)


@router.callback_query(AdminPanel.managing_greeting_watch,
                       AdminCallback.filter(F.action == AdminMenuAction.set_greeting_message))
async def request_new_greeting_message(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await callback.message.edit_text(
        text="Please enter a new greeting message. Don't forget to include a hashtag like #bio or #greeting. Add %USERNAME% if you want to include the username in the message.")
    await state.update_data(group_id=callback_data.group_id)
    await state.update_data(message_id=callback.message.message_id)
    await state.set_state(AdminPanel.setting_greeting_message)


@router.message(AdminPanel.setting_greeting_message)
async def set_new_greeting_message(message: Message, state: FSMContext):
    print('we are in admin interactions')
    group_id = await state.get_value("group_id")
    print(f'group id is:{group_id}')
    try:
        group = await admin_service.set_group_greeting(group_id, message)
    except ValueError as e:
        await bot.send_message(message.chat.id, e.args[0])
        group = await group_service.get_or_create_group(group_id)
    try:
        await bot.delete_message(message.chat.id, await state.get_value("message_id"))
    except Exception as e:
        pass
    keyboard = await build_greeting_watch_keyboard(group_id, group_service)

    message_text = f"{group.title} has the following greeting message:\n\n" \
                   f"{group.greeting_message}"

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
        print(e)
        if e.args[0] == "greeting_watch":
            await callback.message.edit_text(text=e.args[1])
            keyboard = await build_greeting_watch_keyboard(group_id, group_service)
            await callback.message.edit_reply_markup(reply_markup=keyboard)
        return

    await callback.answer(
        f"Feature {feature_name} changed."
    )

    if await state.get_state() == AdminPanel.managing_features:
        message_text = f"{feature_name} was updated successfully!\n\n" \
                       f"Selected group: {group.title}. What do you want to do with it?"
        keyboard = await build_main_features_keyboard(group_id, group_service)
        await callback.message.edit_text(text=message_text)
        await callback.message.edit_reply_markup(reply_markup=keyboard)

    elif await state.get_state() == AdminPanel.managing_greeting_watch:
        message_text = f"{feature_name} was updated successfully!\n\n" \
                       f"{group.title} has the following greeting message:\n\n" \
                       f"{group.greeting_message}"
        keyboard = await build_greeting_watch_keyboard(group_id, group_service)
        await callback.message.edit_text(text=message_text)
        await callback.message.edit_reply_markup(reply_markup=keyboard)

    else:
        await callback.message.edit_text(text="Unknown state.")


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.back))
async def go_back(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    if callback_data.level == 2:
        await state.set_state(AdminPanel.managing_features)
        await process_group_selection(callback, callback_data, state)
    elif callback_data.level == 1:
        await state.set_state(AdminPanel.choosing_group)
        my_groups = await admin_service.get_my_groups(callback.from_user.id)

        welcome_text = (
            f"Hello, my dear tester {callback.from_user.full_name}!\n\n"
            f"Please select a group from the list below:"
        )

        keyboard = await build_group_selection_keyboard(my_groups)

        await callback.message.edit_text(welcome_text)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    else:
        await callback.message.edit_text(text="Back to main menu.")


@router.message(Command('quit'))
async def quit_admin_interface(message: Message, state: FSMContext):
    await message.answer("Bye!")
    current_state = await state.get_state()
    print(f"current state is: {current_state}")
    await state.clear()
    current_state = await state.get_state()
    print(f"and now current state is: {current_state}")


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.quit))
async def quit_admin_interface_from_callback(callback: CallbackQuery, state: FSMContext):
    await quit_admin_interface(callback.message, state)
