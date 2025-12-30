from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.core import bot
from app.db.session import async_session_maker
from app.schemas.states import AdminPanel, GreetingWatch
from app.schemas.callbacks import AdminCallback, AdminMenuAction, GroupFeature
from app.helpers.admin_interactions import build_greeting_watch_keyboard, \
    edit_message_safely, build_greeting_watch_text, delete_messages_safely
from app.services.admin import AdminService
from app.services.group import GroupService
from app.services.group_permission import GroupPermissionService

router = Router()
group_permission_service = GroupPermissionService(async_session_maker)
group_service = GroupService(async_session_maker)
admin_service = AdminService(async_session_maker, group_service, group_permission_service)


@router.callback_query(AdminPanel.managing_features, AdminCallback.filter(
    (F.feature_name == GroupFeature.greeting_watch) & (F.action == AdminMenuAction.open_feature)))
async def open_greeting_watch(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    group = await group_service.get_or_create_group(callback_data.group_id)
    keyboard = await build_greeting_watch_keyboard(group.id, group_service)

    message_text = await build_greeting_watch_text(group.id, callback.from_user.username, group_service)

    await edit_message_safely(message=callback.message, text=message_text, reply_markup=keyboard)
    await state.set_state(GreetingWatch.managing_greeting_watch)

@router.callback_query(GreetingWatch.managing_greeting_watch,
                       AdminCallback.filter(F.action == AdminMenuAction.set_greeting_message))
async def request_new_greeting_message(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await edit_message_safely(message=callback.message,
                              text="Please enter a new greeting message. Don't forget to include a hashtag like #bio or #greeting."
                                   "Add %USERNAME% if you want to include the username in the message.")
    await state.update_data(group_id=callback_data.group_id)
    await state.update_data(message_id=callback.message.message_id)
    await state.set_state(GreetingWatch.setting_greeting_message)


@router.message(GreetingWatch.setting_greeting_message)
async def set_new_greeting_message(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    message_id = await state.get_value("message_id")
    try:
        group = await admin_service.set_group_greeting(group_id, message)
    except ValueError as e:
        await bot.send_message(message.chat.id, e.args[0])
        group = await group_service.get_or_create_group(group_id)
    await delete_messages_safely(message.chat.id, [message_id, message.message_id])

    keyboard = await build_greeting_watch_keyboard(group_id, group_service)

    message_text = await build_greeting_watch_text(group_id, message.from_user.username, group_service)

    await bot.send_message(message.chat.id, message_text, reply_markup=keyboard)
    await state.set_state(GreetingWatch.managing_greeting_watch)


@router.callback_query(GreetingWatch.managing_greeting_watch,
                       AdminCallback.filter(F.action == AdminMenuAction.set_reminder_message))
async def request_new_reminder_message(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await edit_message_safely(message=callback.message,
                              text="Please enter a new reminder message that will be followed by the repeated greeting."
                                   "Add %USERNAME% if you want to include the username in the message.")
    await state.update_data(group_id=callback_data.group_id)
    await state.update_data(message_id=callback.message.message_id)
    await state.set_state(GreetingWatch.setting_reminder_message)


@router.message(GreetingWatch.setting_reminder_message)
async def set_new_reminder_message(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    message_id = await state.get_value("message_id")
    try:
        group = await admin_service.set_group_reminder(group_id, message.text)
    except ValueError as e:
        await bot.send_message(message.chat.id, e.args[0])
        group = await group_service.get_or_create_group(group_id)

    await delete_messages_safely(message.chat.id, [message_id, message.message_id])

    keyboard = await build_greeting_watch_keyboard(group_id, group_service)

    message_text = await build_greeting_watch_text(group_id, message.from_user.username, group_service)

    await bot.send_message(message.chat.id, message_text, reply_markup=keyboard)
    await state.set_state(GreetingWatch.managing_greeting_watch)