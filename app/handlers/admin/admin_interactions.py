from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.core import bot
from app.config import settings
from app.db.session import async_session_maker
from app.schemas.states import AdminPanel, GreetingWatch
from app.schemas.callbacks import AdminCallback, AdminMenuAction
from app.helpers.admin_interactions import build_main_features_keyboard, build_greeting_watch_keyboard, \
    build_group_selection_keyboard, edit_message_safely, delete_messages_safely
from app.services.admin import AdminService
from app.services.group import GroupService
from app.services.group_permission import GroupPermissionService
from app.services.s3_backup import S3BackupService
from app.services.translation import t_for

router = Router()
group_permission_service = GroupPermissionService(async_session_maker)
group_service = GroupService(async_session_maker)
admin_service = AdminService(async_session_maker, group_service, group_permission_service)


@router.message(Command("manage"))
async def start_command(message: Message, state: FSMContext):
    if message.chat.type != "private":
        text = await t_for(key="admin_interactions.errors.command_available_in_private_chats", user_id=message.from_user.id, default_locale=message.from_user.language_code)
        await message.answer(text)
        return

    my_groups = await admin_service.get_my_groups(message.from_user.id)
    if not my_groups:
        text = await t_for(key="admin_interactions.errors.no_admin_groups",
                           user_id=message.from_user.id, default_locale=message.from_user.language_code)
        await message.answer(text)
        return

    welcome_text = await t_for(key="admin_interactions.hello",
                           user_id=message.from_user.id, default_locale=message.from_user.language_code, name=message.from_user.full_name)

    keyboard = await build_group_selection_keyboard(my_groups)

    await bot.send_message(message.from_user.id, welcome_text, reply_markup=keyboard)

    await state.set_state(AdminPanel.choosing_group)


@router.message(Command("get_latest_backup"))
async def restore_backup(message: Message, state: FSMContext):
    await delete_messages_safely(message.chat.id, [message.message_id])
    if message.from_user.id != settings.ADMIN_TELEGRAM_ID:
        text = await t_for(key="admin_interactions.backups.restore.not_admin",
                           user_id=message.from_user.id, default_locale=message.from_user.language_code)
        await bot.send_message(message.chat.id, text=text)
        return

    try:
        s3 = S3BackupService()
        await s3.download_latest_backup()
        text = await t_for(key="admin_interactions.backups.restore.success",
                           user_id=message.from_user.id, default_locale=message.from_user.language_code)
        await bot.send_message(message.chat.id, text)
    except Exception as e:
        text = await t_for(key="admin_interactions.backups.restore.error",
                           user_id=message.from_user.id, default_locale=message.from_user.language_code, error=str(e))
        await bot.send_message(message.chat.id, text)


@router.message(Command("run_backup"))
async def force_backup(message: Message, state: FSMContext):
    await delete_messages_safely(message.chat.id, [message.message_id])
    if message.from_user.id != settings.ADMIN_TELEGRAM_ID:
        text = await t_for(key="admin_interactions.backups.run.not_admin",
                           user_id=message.from_user.id, default_locale=message.from_user.language_code)
        await bot.send_message(message.chat.id, text)
        return

    try:
        s3 = S3BackupService()
        stats = await s3.process_backups()

        if stats["found"] > 0:
            text = await t_for(key="admin_interactions.backups.run.success",
                               user_id=message.from_user.id, default_locale=message.from_user.language_code,
                               uploaded=stats["uploaded"], found=stats["found"], failed=stats["failed"])
            await bot.send_message(message.chat.id, text)
        else:
            text = await t_for(key="admin_interactions.backups.run.no_backups",
                               user_id=message.from_user.id, default_locale=message.from_user.language_code)
            await bot.send_message(message.chat.id, "No backup files found.")
    except Exception as e:
        text = await t_for(key="admin_interactions.backups.run.error",
                           user_id=message.from_user.id, default_locale=message.from_user.language_code,
                           error=str(e))
        await bot.send_message(message.chat.id, text)


@router.callback_query(AdminPanel.choosing_group, AdminCallback.filter(F.action == AdminMenuAction.select_group))
async def process_group_selection(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    group_id = callback_data.group_id
    group = await group_service.get_or_create_group(group_id)
    features = await group_service.get_features(group_id)
    can_manage_payments = callback.from_user.id == settings.ADMIN_TELEGRAM_ID
    keyboard = await build_main_features_keyboard(group_id, features, can_manage_payments)
    text = await t_for(key="admin_interactions.group_management.group_selected",
                       user_id=callback.from_user.id, default_locale=callback.from_user.language_code,
                       title=group.title)

    await edit_message_safely(message=callback.message,
                              text=text,
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
    feature_updated = await t_for(key="admin_interactions.group_management.feature_updated",
                                  user_id=callback.from_user.id, default_locale=callback.from_user.language_code,
                                  feature=feature_name.replace("_", " ").capitalize())
    await callback.answer(feature_updated)

    if await state.get_state() == AdminPanel.managing_features:
        group_selected = await t_for(key="admin_interactions.group_management.group_selected",
                       user_id=callback.from_user.id, default_locale=callback.from_user.language_code,
                       title=group.title)
        features = await group_service.get_features(group_id)
        keyboard = await build_main_features_keyboard(group_id, features,
                                                      callback.from_user.id == settings.ADMIN_TELEGRAM_ID)
        await edit_message_safely(message=callback.message, text=f"{feature_updated}\n\n{group_selected}", reply_markup=keyboard)

    elif await state.get_state() == GreetingWatch.managing_greeting_watch:
        has_greeting_message = await t_for(key="admin_interactions.group_management.has_greeting_message",
                                           user_id=callback.from_user.id, default_locale=callback.from_user.language_code,
                                           title=group.title)
        message_text = f"{feature_updated}\n\n" \
                       f"{has_greeting_message}\n\n" \
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

        welcome_text = await t_for(key="admin_interactions.hello", user_id=callback.from_user.id,
                                   default_locale=callback.from_user.language_code, name=callback.from_user.full_name)

        keyboard = await build_group_selection_keyboard(my_groups)

        await edit_message_safely(message=callback.message, text=welcome_text, reply_markup=keyboard)
    else:
        text = await t_for(key="admin_interactions.back_to_main", user_id=callback.from_user.id,
                           default_locale=callback.from_user.language_code)
        await edit_message_safely(message=callback.message, text=text)


@router.message(Command('quit'))
async def quit_admin_interface(message: Message, state: FSMContext):
    await message.answer("Bye!")
    await state.clear()


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.quit))
async def quit_admin_interface_from_callback(callback: CallbackQuery, state: FSMContext):
    await quit_admin_interface(callback.message, state)
