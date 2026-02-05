from urllib.parse import urlparse

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger

from app.bot.core import bot
from app.config import settings
from app.db.models import message
from app.db.session import async_session_maker
from app.handlers.admin.admin_interactions import process_group_selection
from app.helpers.admin_interactions import edit_message_safely, build_confirm_announcement_keyboard, \
    build_confirm_pin_keyboard, delete_messages_safely, build_skip_button, build_main_features_keyboard, \
    build_confirm_ai_vs_human_announcement_keyboard, \
    build_topics_selection_keyboard, build_yes_no_keyboard
from app.schemas.callbacks import AdminCallback, AdminMenuAction
from app.schemas.states import AdminPanel, Announcement
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


@router.callback_query(AdminPanel.managing_features,
                       AdminCallback.filter(F.action == AdminMenuAction.make_announcement))
async def select_group_topic(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    group = await group_service.get_group(callback_data.group_id)
    if group.topics:
        topics = await group_service.get_topics(callback_data.group_id)
        keyboard = await build_topics_selection_keyboard(topics=topics, group_id=callback_data.group_id)
        text = await t_for(key="admin_interactions.create_announcement.select_topic",
                           user_id=callback.from_user.id)
        return await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)
    else:
        return await set_announcement_text(callback=callback, callback_data=callback_data, state=state)


@router.callback_query(AdminPanel.managing_features, AdminCallback.filter(F.action == AdminMenuAction.set_topic))
async def set_announcement_text(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await state.update_data(topic_id=callback_data.topic_id, group_id=callback_data.group_id,
                            message_id=callback.message.message_id)
    await state.set_state(Announcement.creating_announcement)
    group = await group_service.get_group(callback_data.group_id)
    text = await t_for(key="admin_interactions.create_announcement.enter_text",
                       user_id=callback.from_user.id,
                       group_name=group.title)
    await edit_message_safely(message=callback.message, text=text)


@router.message(Announcement.creating_announcement, F.text)
async def show_confirmation_dialogue(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    message_id = await state.get_value("message_id")
    await state.update_data(announcement_text=message.text)
    await delete_messages_safely(message.chat.id, [message.message_id, message_id])
    keyboard = await build_confirm_announcement_keyboard(group_id)
    confirm_announcement_text = await t_for(key="admin_interactions.create_announcement.confirm_announcement",
                                            user_id=message.from_user.id)
    confirmation_text = f"{confirm_announcement_text}\n\n<blockquote>{message.text}</blockquote>"
    await bot.send_message(message.chat.id, text=confirmation_text, reply_markup=keyboard)
    await state.set_state(Announcement.confirming_announcement)


@router.callback_query(Announcement.confirming_announcement,
                       AdminCallback.filter((F.action == AdminMenuAction.rewrite_announcement) & F.level == 2))
async def rewrite_announcement(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    original_text = await state.get_value("announcement_text")
    ai_service = AIService()
    rewritten_text = await ai_service.rewrite_announcement(original_text=original_text)
    await state.update_data(ai_announcement_text=rewritten_text)
    final_text = f"Original announcement: <blockquote>{original_text}</blockquote>\n\nAI version: <blockquote>{rewritten_text}</blockquote>"
    keyboard = await build_confirm_ai_vs_human_announcement_keyboard(callback_data.group_id)
    await edit_message_safely(message=callback.message, text=final_text, reply_markup=keyboard)


@router.callback_query(Announcement.confirming_announcement,
                       AdminCallback.filter((F.action == AdminMenuAction.confirm_announcement) & F.level == 2))
@router.callback_query(Announcement.confirming_announcement,
                       AdminCallback.filter((F.action == AdminMenuAction.confirm_ai_announcement) & F.level == 2))
async def select_announcement_text(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    if callback_data.action == AdminMenuAction.confirm_announcement:
        final_announcement_text = await state.get_value("announcement_text")
    elif callback_data.action == AdminMenuAction.confirm_ai_announcement:
        final_announcement_text = await state.get_value("ai_announcement_text")
    else:
        logger.error(f"Invalid action in send_announcement: {callback_data.action}")
        return
    group_id = await state.get_value("group_id")
    topic_id = await state.get_value("topic_id")
    announcement = await message_service.create_message(group_id=group_id, topic_id=topic_id,
                                                        text=final_announcement_text, is_published=False,
                                                        is_pinned=False)
    await state.update_data(announcement_id=announcement.id)
    # await state.update_data(final_announcement_text=final_announcement_text, message_id=callback.message.message_id, user_id=callback.message.from_user.id)
    # await state.set_state(Announcement.adding_announcement_picture)
    keyboard = await build_yes_no_keyboard(yes_text="Yes", no_text="No",
                                           yes_action=AdminMenuAction.add_announcement_picture,
                                           no_action=AdminMenuAction.skip_adding_picture)

    await edit_message_safely(message=callback.message, text="Do you want to add a picture?", reply_markup=keyboard)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.add_announcement_picture))
async def show_add_picture_dialogue(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Announcement.adding_announcement_picture)
    await state.update_data(message_id=callback.message.message_id)
    text = "Please send me a picture that you want to add"
    await edit_message_safely(message=callback.message, text=text)


@router.message(Announcement.adding_announcement_picture)
async def add_announcement_picture(message: Message, state: FSMContext):
    message_id = await state.get_value("message_id")
    await delete_messages_safely(message.chat.id, [message.message_id, message_id])
    picture = None
    if message.photo:
        picture = message.photo[-1].file_id
    elif message.document:
        reply = await bot.send_message(message.chat.id, "Please send me a picture as a photo, not as a file.")
    else:
        logger.error(f"Invalid data in add_announcement_picture: {message}")
        reply = await bot.send_message(message.chat.id, "That is not an image! Please send me a picture.")
    if picture:
        announcement_id = await state.get_value("announcement_id")
        announcement = await message_service.update_message(announcement_id=announcement_id, picture=picture)
        text = "<pre>Here is your announcement:</pre>\n\n"
        question = "\n\n<pre>Do you want to send this announcement?</pre>"
        keyboard = await build_yes_no_keyboard(yes_text="Send", no_text="cancel",
                                               yes_action=AdminMenuAction.send_announcement,
                                               no_action=AdminMenuAction.select_group)
        reply = await bot.send_photo(chat_id=message.chat.id, photo=announcement.picture,
                                     caption=text + announcement.text + question, reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.skip_adding_picture))
async def show_send_announcement_dialogue(callback: CallbackQuery, state: FSMContext):
    await delete_messages_safely(chat_id=callback.message.chat.id, message_ids=[callback.message.message_id])
    announcement_id = await state.get_value("announcement_id")
    announcement = await message_service.get_message(announcement_id=announcement_id)
    text = "<pre>Here is your announcement:</pre>\n\n"
    question = "\n\n<pre>Do you want to send this announcement?</pre>"
    keyboard = await build_yes_no_keyboard(yes_text="Send", no_text="Cancel",
                                           yes_action=AdminMenuAction.send_announcement,
                                           no_action=AdminMenuAction.select_group)
    if announcement.picture:
        reply = await bot.send_photo(chat_id=callback.message.chat.id, photo=announcement.picture,
                                     caption=text + announcement.text + question, reply_markup=keyboard)
    else:
        reply = await bot.send_message(chat_id=callback.message.chat.id, text=text + announcement.text + question,
                                       reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.send_announcement))
async def send_announcement(callback: CallbackQuery, state: FSMContext):
    announcement_id = await state.get_value("announcement_id")
    announcement = await message_service.get_message(announcement_id=announcement_id)
    # can_pin_announcements = await group_permission_service.check_permission(announcement.group_id, "can_pin_messages")

    if announcement.picture:
        result = await bot.send_photo(chat_id=announcement.group_id, message_thread_id=announcement.topic_id,
                                      photo=announcement.picture, caption=announcement.text)
    else:
        result = await bot.send_message(chat_id=announcement.group_id, message_thread_id=announcement.topic_id,
                                        text=announcement.text)
    if not result:
        failed_to_send_text = await t_for(key="admin_interactions.create_announcement.failed_to_send_announcement",
                                          user_id=callback.from_user.id)
        await callback.answer(failed_to_send_text)
        return

    await message_service.update_message(announcement_id=announcement.id, message_id=result.message_id,
                                         is_published=True)
    await delete_messages_safely(callback.message.chat.id, [callback.message.message_id])

    question = "Announcement published!\nDo you want to add buttons to it?"
    keyboard = await build_yes_no_keyboard(yes_text="Add buttons", no_text="Cancel",
                                           yes_action=AdminMenuAction.add_announcement_button,
                                           no_action=AdminMenuAction.select_group)

    reply = await bot.send_message(chat_id=callback.message.chat.id, text=question, reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.add_announcement_button))
async def add_button_name_dialogue(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Announcement.setting_button_name)
    await state.update_data(button_name="")
    announcement_id = await state.get_value("announcement_id")
    group_id = await state.get_value("group_id")
    text = "Please write the name of the button you want to add."
    keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                       action=AdminMenuAction.select_group, button_name="Cancel")
    await edit_message_safely(callback.message, text=text, reply_markup=keyboard)


@router.message(Announcement.setting_button_name, F.text)
async def set_announcement_button_name(message: Message, state: FSMContext):
    message_id = await state.get_value("message_id")
    group_id = await state.get_value("group_id")
    await delete_messages_safely(message.chat.id, [message_id, message.message_id])

    if len(message.text) > 64:
        title_is_too_long_text = await t_for(key="admin_interactions.create_announcement.payment.title_too_long",
                                             user_id=message.from_user.id)
        reply = await bot.send_message(chat_id=message.chat.id, text=title_is_too_long_text)
    else:
        await state.update_data(button_name=message.text)
        text = f"Your button will have the following name:\n\n<blockquote>{message.text}</blockquote>\n\nIs that correct?"
        keyboard = await build_yes_no_keyboard(yes_text="Yes", no_text="No",
                                               yes_action=AdminMenuAction.set_announcement_button_name,
                                               no_action=AdminMenuAction.add_announcement_button,
                                               group_id=group_id)
        reply = await bot.send_message(chat_id=message.chat.id, text=text, reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.set_announcement_button_name))
async def add_button_link_dialogue(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Announcement.setting_button_link)
    await state.update_data(button_link="")
    announcement_id = await state.get_value("announcement_id")
    group_id = await state.get_value("group_id")
    text = "Please write the link that the button will lead to."
    keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                       action=AdminMenuAction.select_group, button_name="Cancel")
    await edit_message_safely(callback.message, text=text, reply_markup=keyboard)


@router.message(Announcement.setting_button_link, F.text)
async def set_announcement_button_link(message: Message, state: FSMContext):
    message_id = await state.get_value("message_id")
    group_id = await state.get_value("group_id")
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
        button_name = await state.get_value("button_name")
        text = f"Your button '{button_name}' will lead to:\n<blockquote>{message.text.strip()}</blockquote>\n\nIs that correct?"
        keyboard = await build_yes_no_keyboard(yes_text="Yes", no_text="No",
                                               yes_action=AdminMenuAction.set_announcement_button_link,
                                               no_action=AdminMenuAction.set_announcement_button_name,
                                               group_id=group_id)
        reply = await bot.send_message(chat_id=message.chat.id, text=text, reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.set_announcement_button_link))
async def create_and_publish_announcement_button(callback: CallbackQuery, state: FSMContext):
    button_name = await state.get_value("button_name")
    button_link = await state.get_value("button_link")
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    try:
        announcement = await message_service.get_message(announcement_id=announcement_id)
        await button_service.create_button(message_id=announcement.id, button_text=button_name, button_link=button_link)
        await message_service.add_buttons_to_announcement(message_id=announcement.message_id,
                                                          group_id=announcement.group_id)
    except Exception as e:
        logger.error(e)
        await callback.answer("Failed to create button. Please try again later.")
        await edit_message_safely(callback.message, text=str(e))
        return

    text = f"Button '{button_name}' created and published successfully.\nWould you like to add another button?"
    keyboard = await build_yes_no_keyboard(yes_text="Add more buttons", no_text="Done",
                                           yes_action=AdminMenuAction.add_announcement_button,
                                           no_action=AdminMenuAction.select_group, group_id=group_id)
    await edit_message_safely(callback.message, text=text, reply_markup=keyboard)


@router.callback_query(Announcement.confirming_pin,
                       AdminCallback.filter((F.action == AdminMenuAction.confirm_pin) & F.level == 2))
async def pin_announcement(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await bot.pin_chat_message(chat_id=callback_data.group_id, message_id=callback_data.announcement_id)
    await message_service.pin_message(group_id=callback_data.group_id, message_id=callback_data.announcement_id)
    success_text = await t_for(key="admin_interactions.create_announcement.pin.pinned",
                               user_id=callback.from_user.id)
    await callback.answer(success_text)

    await state.set_state(AdminPanel.managing_features)
    await process_group_selection(callback, callback_data, state)
