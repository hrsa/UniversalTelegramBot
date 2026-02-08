from urllib.parse import urlparse

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger

from app.bot.core import bot
from app.db.session import async_session_maker
from app.helpers.admin_interactions import edit_message_safely, delete_messages_safely, build_skip_button, \
    build_announcement_mgmt_message, \
    build_announcement_delete_confirmation, build_modify_ai_vs_human_announcement_keyboard, \
    build_modify_buttons_keyboard, build_edit_button_keyboard, build_yes_no_keyboard
from app.schemas.callbacks import AdminCallback, AdminMenuAction
from app.schemas.states import Announcement
from app.services.admin import AdminService
from app.services.ai import AIService
from app.services.group import GroupService
from app.services.group_permission import GroupPermissionService
from app.services.message import MessageService
from app.services.message_button import ButtonService
from app.services.translation import t_for

router = Router()
group_permission_service = GroupPermissionService(async_session_maker)
group_service = GroupService(async_session_maker)
admin_service = AdminService(async_session_maker, group_service, group_permission_service)
message_service = MessageService(async_session_maker)
button_service = ButtonService(async_session_maker)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.manage_announcements))
async def manage_announcements(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await state.set_state(Announcement.managing_announcements)
    offset = callback_data.announcement_offset if callback_data.announcement_offset is not None else 0
    limit = 1
    can_pin_announcements = await group_permission_service.check_permission(callback_data.group_id, "can_pin_messages")

    announcements, count = await group_service.get_group_announcements(group_id=callback_data.group_id, offset=offset,
                                                                       limit=limit)
    await state.update_data(group_id=callback_data.group_id,
                            announcement_id=announcements[0].id if announcements else None)
    text, keyboard = await build_announcement_mgmt_message(announcement=announcements[0] if announcements else None,
                                                           group_id=callback_data.group_id, count=count, offset=offset,
                                                           can_pin_announcements=can_pin_announcements)
    await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)


@router.callback_query(Announcement.managing_announcements,
                       AdminCallback.filter(F.action == AdminMenuAction.modify_announcement_buttons))
async def show_modify_buttons_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    announcement = await message_service.get_message(announcement_id=callback_data.announcement_id)
    keyboard = await build_modify_buttons_keyboard(announcement=announcement)
    text = "Please click on the button you want to modify"
    await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)


@router.callback_query(Announcement.managing_announcements,
                       AdminCallback.filter(F.action == AdminMenuAction.add_announcement_button_name))
async def show_add_button_name_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await state.update_data(announcement_id=callback_data.announcement_id, message_id=callback.message.message_id)
    await state.set_state(Announcement.adding_button_name)
    keyboard = await build_skip_button(announcement_id=callback_data.announcement_id, group_id=callback_data.group_id,
                                       action=AdminMenuAction.back, button_name="Cancel")
    text = "Please write the name of the button you want to add."
    await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)

@router.message(Announcement.adding_button_name, F.text)
async def add_button_name(message: Message, state: FSMContext):
    message_id = await state.get_value("message_id")
    group_id = await state.get_value("group_id")
    await delete_messages_safely(message.chat.id, [message_id, message.message_id])

    if len(message.text) > 64:
        title_is_too_long_text = await t_for(key="admin_interactions.create_announcement.payment.title_too_long",
                                             user_id=message.from_user.id)
        reply = await bot.send_message(chat_id=message.chat.id, text=title_is_too_long_text)
    else:
        await state.update_data(button_name=message.text)
        await state.set_state(Announcement.managing_announcements)
        text = f"Your button will have the following name:\n\n<blockquote>{message.text}</blockquote>\n\nIs that correct?"
        keyboard = await build_yes_no_keyboard(yes_text="Yes", no_text="No",
                                               yes_action=AdminMenuAction.add_announcement_button_link,
                                               no_action=AdminMenuAction.add_announcement_button_name,
                                               group_id=group_id)
        reply = await bot.send_message(chat_id=message.chat.id, text=text, reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id)


@router.callback_query(Announcement.managing_announcements,
                       AdminCallback.filter(F.action == AdminMenuAction.add_announcement_button_link))
async def show_add_button_link_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await state.set_state(Announcement.adding_button_link)
    await state.update_data(button_link="")
    announcement_id = await state.get_value("announcement_id")
    group_id = await state.get_value("group_id")
    text = "Please write the link that the button will lead to."
    keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                       action=AdminMenuAction.back, button_name="Cancel")
    await edit_message_safely(callback.message, text=text, reply_markup=keyboard)

@router.message(Announcement.adding_button_link, F.text)
async def add_button_link(message: Message, state: FSMContext):
    message_id = await state.get_value("message_id")
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    await delete_messages_safely(message.chat.id, [message_id, message.message_id])

    parsed = urlparse(message.text.strip())
    is_valid_url = parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    if not is_valid_url:
        reply = await bot.send_message(
            chat_id=message.chat.id,
            text="That doesn't look like a valid URL. Please send a full link starting with http:// or https://"
        )
        await state.update_data(message_id=reply.message_id)
    else:
        await state.update_data(button_link=message.text.strip())
        await state.set_state(Announcement.managing_announcements)
        button_name = await state.get_value("button_name")
        text = f"Your button '{button_name}' will lead to:\n<blockquote>{message.text.strip()}</blockquote>\n\nIs that correct?"
        keyboard = await build_yes_no_keyboard(yes_text="Yes", no_text="No",
                                               yes_action=AdminMenuAction.confirm_and_add_button,
                                               no_action=AdminMenuAction.add_announcement_button_link,
                                               group_id=group_id, announcement_id=announcement_id)
        reply = await bot.send_message(chat_id=message.chat.id, text=text, reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id)

@router.callback_query(Announcement.managing_announcements,
                       AdminCallback.filter(F.action == AdminMenuAction.confirm_and_add_button))
async def confirm_and_add_button(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    button_name = await state.get_value("button_name")
    button_link = await state.get_value("button_link")
    announcement_id = await state.get_value("announcement_id")
    try:
        announcement = await message_service.get_message(announcement_id=announcement_id)
        await button_service.create_button(message_id=announcement.id, button_text=button_name, button_link=button_link)
        await message_service.add_buttons_to_announcement(message_id=announcement.message_id,
                                                          group_id=announcement.group_id)
        await show_modify_buttons_dialogue(callback, callback_data, state)
    except Exception as e:
        logger.error(e)
        await callback.answer("Failed to create button. Please try again later.")
        await edit_message_safely(callback.message, text=str(e))
        return


@router.callback_query(Announcement.managing_announcements,
                       AdminCallback.filter(F.action == AdminMenuAction.edit_announcement_button))
async def show_edit_button_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    button = await button_service.get_button(callback_data.button_id)
    keyboard = await build_edit_button_keyboard(button_id=callback_data.button_id)
    text = (f"Button name:\n"
            f"<pre>{button.text}</pre>\n\n"
            f"Button link:\n"
            f"<pre>{button.link}</pre>")
    await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)


@router.callback_query(Announcement.managing_announcements,
                       AdminCallback.filter(F.action == AdminMenuAction.edit_button_text))
async def show_edit_button_name_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await state.set_state(Announcement.editing_button_name)
    announcement_id = await state.get_value("announcement_id")
    group_id = await state.get_value("group_id")
    await state.update_data(button_id=callback_data.button_id, message_id=callback.message.message_id)
    text = f"Please write a new name for the button"
    keyboard = await build_skip_button(button_name="Cancel", action=AdminMenuAction.manage_announcements,
                                       announcement_id=announcement_id, group_id=group_id)
    await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)


@router.message(Announcement.editing_button_name, F.text)
async def modify_button_name(message: Message, state: FSMContext):
    message_id = await state.get_value("message_id")
    button_id = await state.get_value("button_id")
    await delete_messages_safely(message.chat.id, [message_id, message.message_id])

    if len(message.text) > 64:
        title_is_too_long_text = await t_for(key="admin_interactions.create_announcement.payment.title_too_long",
                                             user_id=message.from_user.id)
        reply = await bot.send_message(chat_id=message.chat.id, text=title_is_too_long_text)
    else:
        button = await button_service.update_button(button_id=button_id, text=message.text)
        await message_service.add_buttons_to_announcement(message_id=button.message.message_id,
                                                          group_id=button.message.group_id)
        await state.set_state(Announcement.managing_announcements)
        keyboard = await build_edit_button_keyboard(button_id=button_id)
        text = (f"Button name modified!\n\n"
                f"Button name:\n"
                f"<pre>{button.text}</pre>\n\n"
                f"Button link:\n"
                f"<pre>{button.link}</pre>")
        reply = await bot.send_message(chat_id=message.chat.id, text=text, reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id)


@router.callback_query(Announcement.managing_announcements,
                       AdminCallback.filter(F.action == AdminMenuAction.edit_button_link))
async def show_edit_button_link_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await state.set_state(Announcement.editing_button_link)
    announcement_id = await state.get_value("announcement_id")
    group_id = await state.get_value("group_id")
    await state.update_data(button_id=callback_data.button_id, message_id=callback.message.message_id)
    text = f"Please write a new link for the button"
    keyboard = await build_skip_button(button_name="Cancel", action=AdminMenuAction.manage_announcements,
                                       announcement_id=announcement_id, group_id=group_id)
    await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)


@router.message(Announcement.editing_button_link, F.text)
async def modify_button_link(message: Message, state: FSMContext):
    message_id = await state.get_value("message_id")
    button_id = await state.get_value("button_id")
    await delete_messages_safely(message.chat.id, [message_id, message.message_id])

    parsed = urlparse(message.text.strip())
    is_valid_url = parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    if not is_valid_url:
        reply = await bot.send_message(
            chat_id=message.chat.id,
            text="That doesn't look like a valid URL. Please send a full link starting with http:// or https://"
        )
    else:
        button = await button_service.update_button(button_id=button_id, link=message.text)
        await message_service.add_buttons_to_announcement(message_id=button.message.message_id,
                                                          group_id=button.message.group_id)
        await state.set_state(Announcement.managing_announcements)
        keyboard = await build_edit_button_keyboard(button_id=button_id)
        text = (f"Button link modified!\n\n"
                f"Button name:\n"
                f"<pre>{button.text}</pre>\n\n"
                f"Button link:\n"
                f"<pre>{button.link}</pre>")
        reply = await bot.send_message(chat_id=message.chat.id, text=text, reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id)


@router.callback_query(Announcement.managing_announcements,
                       AdminCallback.filter(F.action == AdminMenuAction.delete_announcement_button))
async def show_delete_button_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    button = await button_service.get_button(button_id=callback_data.button_id)
    text = (f"Are you sure you want to delete button \"<b>{button.text}</b>\"?")
    keyboard = await build_yes_no_keyboard(yes_text="Delete", no_text="Cancel",
                                           yes_action=AdminMenuAction.confirm_delete_announcement_button,
                                           no_action=AdminMenuAction.manage_announcements,
                                           group_id=button.message.group_id,
                                           button_id=button.id,
                                           announcement_id=button.message.id)
    await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)


@router.callback_query(Announcement.managing_announcements,
                       AdminCallback.filter(F.action == AdminMenuAction.confirm_delete_announcement_button))
async def delete_announcement_button(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    button = await button_service.get_button(button_id=callback_data.button_id)
    await button_service.delete_button(button_id=callback_data.button_id)
    await message_service.add_buttons_to_announcement(message_id=button.message.message_id,
                                                      group_id=button.message.group_id)
    await state.set_state(Announcement.managing_announcements)
    await callback.answer(text="Button deleted!")
    announcement = await message_service.get_message(announcement_id=button.message.id)
    if announcement.buttons:
        await show_modify_buttons_dialogue(callback=callback, callback_data=callback_data, state=state)
    else:
        await manage_announcements(callback=callback, callback_data=callback_data, state=state)


@router.callback_query(Announcement.managing_announcements,
                       AdminCallback.filter(F.action == AdminMenuAction.delete_announcement))
async def confirm_announcement_deletion(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    announcement = await message_service.get_message(announcement_id=callback_data.announcement_id)
    text, keyboard = await build_announcement_delete_confirmation(announcement, callback_data.announcement_offset)
    await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)


@router.callback_query(Announcement.managing_announcements,
                       AdminCallback.filter(F.action == AdminMenuAction.rewrite_announcement))
async def rewrite_announcement(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await callback.answer("🤖 Thinking... 🤖")
    announcement = await message_service.get_message(announcement_id=callback_data.announcement_id)
    ai_service = AIService()
    rewritten_text = await ai_service.rewrite_announcement(original_text=announcement.text)
    await state.update_data(ai_announcement_text=rewritten_text)
    final_text = f"Original announcement: <blockquote>{announcement.text}</blockquote>\n\nAI version: <blockquote>{rewritten_text}</blockquote>"
    keyboard = await build_modify_ai_vs_human_announcement_keyboard(group_id=callback_data.group_id,
                                                                    announcement_id=callback_data.announcement_id,
                                                                    offset=callback_data.announcement_offset)
    await edit_message_safely(message=callback.message, text=final_text, reply_markup=keyboard)


@router.callback_query(Announcement.managing_announcements,
                       AdminCallback.filter(F.action == AdminMenuAction.confirm_ai_announcement))
async def confirm_ai_rewrite(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    rewritten_text = await state.get_value("ai_announcement_text")
    announcement = await message_service.update_message(announcement_id=callback_data.announcement_id,
                                                        text=rewritten_text)
    try:
        await bot.edit_message_text(chat_id=announcement.group_id, message_id=announcement.message_id,
                                    text=rewritten_text)
    except Exception as e:
        logger.error(
            f"Error when editing message (id: {callback_data.announcement_id}, group: {callback_data.group_id}): {e}")
    await callback.answer("Announcement updated!")
    await manage_announcements(callback, callback_data, state)


@router.callback_query(Announcement.managing_announcements,
                       AdminCallback.filter(F.action == AdminMenuAction.confirm_delete_announcement))
async def delete_announcement(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    announcement = await message_service.get_message(announcement_id=callback_data.announcement_id)
    await delete_messages_safely(chat_id=callback_data.group_id, message_ids=[announcement.message_id])
    await message_service.delete_message(announcement_id=announcement.id)
    success_text = await t_for(key="admin_interactions.manage_announcement.announcement_deleted",
                               user_id=callback.from_user.id)
    await callback.answer(success_text)
    await manage_announcements(callback, callback_data, state)


@router.callback_query(Announcement.managing_announcements,
                       AdminCallback.filter(F.action == AdminMenuAction.confirm_pin))
async def toggle_pin_message(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    announcement = await message_service.get_message(announcement_id=callback_data.announcement_id)
    if announcement is None:
        logger.warning(f"Announcement {callback_data.announcement_id} not found in database.")
        return

    if announcement.is_pinned:
        await bot.unpin_chat_message(chat_id=announcement.group_id, message_id=announcement.message_id)
        await message_service.unpin_message(group_id=announcement.group_id,
                                            message_id=announcement.message_id)
        text = await t_for(key="admin_interactions.manage_announcement.unpinned", user_id=callback.from_user.id)
    else:
        await bot.pin_chat_message(chat_id=announcement.group_id, message_id=announcement.message_id)
        await message_service.pin_message(group_id=announcement.group_id, message_id=announcement.message_id)
        text = await t_for(key="admin_interactions.manage_announcement.pinned", user_id=callback.from_user.id)

    await callback.answer(text)

    await manage_announcements(callback, callback_data, state)
