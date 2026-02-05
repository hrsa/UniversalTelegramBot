from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger

from app.bot.core import bot
from app.config import settings
from app.db.session import async_session_maker
from app.helpers.admin_interactions import edit_message_safely, delete_messages_safely, build_skip_button, \
    build_announcement_mgmt_message, \
    build_announcement_delete_confirmation, build_modify_ai_vs_human_announcement_keyboard
from app.schemas.callbacks import AdminCallback, AdminMenuAction
from app.schemas.states import Announcement
from app.services.admin import AdminService
from app.services.ai import AIService
from app.services.group import GroupService
from app.services.group_permission import GroupPermissionService
from app.services.message import MessageService
from app.services.stripe_payment import StripePaymentService
from app.services.translation import t_for

router = Router()
group_permission_service = GroupPermissionService(async_session_maker)
group_service = GroupService(async_session_maker)
admin_service = AdminService(async_session_maker, group_service, group_permission_service)
message_service = MessageService(async_session_maker)
stripe_payment_service = StripePaymentService()


@router.callback_query(Announcement.managing_announcements,
                       AdminCallback.filter(F.action == AdminMenuAction.delete_announcement))
async def confirm_announcement_deletion(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    announcement = await message_service.get_message(group_id=callback_data.group_id,
                                                     message_id=callback_data.announcement_id)
    text, keyboard = await build_announcement_delete_confirmation(announcement, callback_data.announcement_offset)
    await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)


@router.callback_query(Announcement.managing_announcements,
                       AdminCallback.filter(F.action == AdminMenuAction.rewrite_announcement))
async def rewrite_announcement(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await callback.answer("🤖 Thinking... 🤖")
    announcement = await message_service.get_message(group_id=callback_data.group_id,
                                                     message_id=callback_data.announcement_id)
    ai_service = AIService()
    rewritten_text = await ai_service.rewrite_announcement(original_text=announcement.text)
    await state.update_data(ai_announcement_text=rewritten_text)
    final_text = f"Original announcement: <blockquote>{announcement.text}</blockquote>\n\nAI version: <blockquote>{rewritten_text}</blockquote>"
    keyboard = await build_modify_ai_vs_human_announcement_keyboard(group_id=callback_data.group_id,
                                                                    announcement_id=callback_data.announcement_id,
                                                                    offset=callback_data.announcement_offset)
    await edit_message_safely(message=callback.message, text=final_text, reply_markup=keyboard)

@router.callback_query(Announcement.managing_announcements, AdminCallback.filter(F.action == AdminMenuAction.confirm_ai_announcement))
async def confirm_ai_rewrite(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    rewritten_text = await state.get_value("ai_announcement_text")
    await message_service.update_text(group_id=callback_data.group_id, message_id=callback_data.announcement_id, text=rewritten_text)
    try:
        await bot.edit_message_text(chat_id=callback_data.group_id, message_id=callback_data.announcement_id, text=rewritten_text)
    except Exception as e:
        logger.error(f"Error when editing message (id: {callback_data.announcement_id}, group: {callback_data.group_id}): {e}")
    await callback.answer("Announcement updated!")
    await manage_announcements(callback, callback_data, state)


@router.callback_query(Announcement.managing_announcements,
                       AdminCallback.filter(F.action == AdminMenuAction.confirm_delete_announcement))
async def delete_announcement(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await delete_messages_safely(chat_id=callback_data.group_id, message_ids=[callback_data.announcement_id])
    await message_service.delete_message(group_id=callback_data.group_id, message_id=callback_data.announcement_id)
    success_text = await t_for(key="admin_interactions.manage_announcement.announcement_deleted",
                               user_id=callback.from_user.id)
    await callback.answer(success_text)
    await manage_announcements(callback, callback_data, state)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.manage_announcements))
async def manage_announcements(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await state.set_state(Announcement.managing_announcements)
    offset = callback_data.announcement_offset if callback_data.announcement_offset is not None else 0
    limit = 1
    can_pin_announcements = await group_permission_service.check_permission(callback_data.group_id, "can_pin_messages")

    announcements, count = await group_service.get_group_announcements(group_id=callback_data.group_id, offset=offset,
                                                                       limit=limit)
    text, keyboard = await build_announcement_mgmt_message(announcement=announcements[0] if announcements else None,
                                                           group_id=callback_data.group_id, count=count, offset=offset,
                                                           can_pin_announcements=can_pin_announcements)
    await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)


@router.callback_query(Announcement.managing_announcements,
                       AdminCallback.filter(F.action == AdminMenuAction.confirm_pin))
async def toggle_pin_message(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
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
            text = await t_for(key="admin_interactions.manage_announcement.unpinned", user_id=callback.from_user.id)
        else:
            await bot.pin_chat_message(chat_id=callback_data.group_id, message_id=callback_data.announcement_id)
            await message_service.pin_message(group_id=callback_data.group_id, message_id=callback_data.announcement_id)
            text = await t_for(key="admin_interactions.manage_announcement.pinned", user_id=callback.from_user.id)

        await callback.answer(text)

    await manage_announcements(callback, callback_data, state)



@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.modify_callback_button_title))
async def show_modify_callback_button_title_dialogue(callback: CallbackQuery, callback_data: AdminCallback,
                                                     state: FSMContext):
    await state.set_state(Announcement.modifying_button_name)
    dialogue_text = await t_for(key="admin_interactions.manage_announcement.modify_button_name_dialogue",
                                user_id=callback.from_user.id)
    back_button_text = await t_for(key="admin_interactions.buttons.back", user_id=callback.from_user.id)
    keyboard = await build_skip_button(announcement_id=callback_data.announcement_id, group_id=callback_data.group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name=back_button_text)
    await state.update_data(message_id=callback.message.message_id, announcement_id=callback_data.announcement_id,
                            group_id=callback_data.group_id)
    await edit_message_safely(callback.message, text=dialogue_text, reply_markup=keyboard)


@router.message(Announcement.modifying_button_name, F.text)
async def modify_button_name_and_show_callback_title_dialogue(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    message_id = await state.get_value("message_id")
    await delete_messages_safely(message.chat.id, [message_id, message.message_id])
    back_button_text = await t_for(key="admin_interactions.buttons.back", user_id=message.from_user.id)
    keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name=back_button_text)

    reply_text = await t_for(key="admin_interactions.create_announcement.payment.title_too_long",
                                 user_id=message.from_user.id)

    reply = await bot.send_message(chat_id=message.chat.id, text=reply_text, reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id, button_name=message.text)
