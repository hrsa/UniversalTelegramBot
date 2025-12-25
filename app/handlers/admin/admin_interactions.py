from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.core import bot
from app.config import settings
from app.db.session import async_session_maker
from app.handlers.admin.states import AdminPanel, GreetingWatch
from app.handlers.admin.callbacks import AdminCallback, AdminMenuAction
from app.helpers.admin_interactions import build_main_features_keyboard, build_greeting_watch_keyboard, \
    build_group_selection_keyboard, edit_message_safely
from app.services.admin import AdminService
from app.services.group import GroupService
from app.services.group_permission import GroupPermissionService

router = Router()
group_permission_service = GroupPermissionService(async_session_maker)
group_service = GroupService(async_session_maker)
admin_service = AdminService(async_session_maker, group_service, group_permission_service)


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
        f"Hello, {message.from_user.full_name}!\n\n"
        f"Please select a group from the list below:"
    )

    keyboard = await build_group_selection_keyboard(my_groups)

    await bot.send_message(message.from_user.id, welcome_text, reply_markup=keyboard)

    await state.set_state(AdminPanel.choosing_group)


@router.callback_query(AdminPanel.choosing_group, AdminCallback.filter(F.action == AdminMenuAction.select_group))
async def process_group_selection(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    group_id = callback_data.group_id
    group = await group_service.get_or_create_group(group_id)
    features = await group_service.get_features(group_id)
    keyboard = await build_main_features_keyboard(group_id, features,
                                                  callback.from_user.id == settings.ADMIN_TELEGRAM_ID)

    await edit_message_safely(message=callback.message,
                              text=f"Selected group: {group.title}. What do you want to do with it?",
                              reply_markup=keyboard)
    await state.set_state(AdminPanel.managing_features)



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
        features = await group_service.get_features(group_id)
        keyboard = await build_main_features_keyboard(group_id, features,
                                                      callback.from_user.id == settings.ADMIN_TELEGRAM_ID)
        await edit_message_safely(message=callback.message, text=message_text, reply_markup=keyboard)

    elif await state.get_state() == GreetingWatch.managing_greeting_watch:
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
            f"Hello, {callback.from_user.full_name}!\n\n"
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
