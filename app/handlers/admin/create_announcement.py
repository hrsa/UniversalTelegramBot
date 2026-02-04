from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger

from app.bot.core import bot
from app.config import settings
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
from app.services.translation import t_for

router = Router()
group_permission_service = GroupPermissionService(async_session_maker)
group_service = GroupService(async_session_maker)
admin_service = AdminService(async_session_maker, group_service, group_permission_service)
message_service = MessageService(async_session_maker)


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
        await state.update_data(topic_id=callback_data.topic_id, group_id=callback_data.group_id, message_id=callback.message.message_id)
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
    announcement = await message_service.create_message(group_id=group_id, topic_id=topic_id, text=final_announcement_text, is_published=False, is_pinned=False)
    await state.update_data(announcement_id=announcement.id)
    # await state.update_data(final_announcement_text=final_announcement_text, message_id=callback.message.message_id, user_id=callback.message.from_user.id)
    # await state.set_state(Announcement.adding_announcement_picture)
    keyboard = await build_yes_no_keyboard(yes_text="Yes", no_text="No", yes_action=AdminMenuAction.add_announcement_picture, no_action=AdminMenuAction.skip_adding_picture)

    await edit_message_safely(message=callback.message, text="Do you want to add a picture?", reply_markup=keyboard)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.add_announcement_picture))
async def show_add_picture_dialogue(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Announcement.adding_announcement_picture)
    await state.update_data(message_id=callback.message.message_id)
    text = "Please send me a picture that you want to add"
    await edit_message_safely(message=callback.message,text=text)


@router.message(Announcement.adding_announcement_picture)
async def add_announcement_picture(message: Message, state: FSMContext):
    message_id = await state.get_value("message_id")
    await delete_messages_safely(message.chat.id, [message.message_id, message_id])
    picture = None
    if message.photo:
        picture = message.photo[-1].file_id
    elif message.document:
        message = await bot.send_message(message.chat.id, "Please send me a picture as a photo, not as a file.")
    else:
        logger.error(f"Invalid data in add_announcement_picture: {message}")
        message = await bot.send_message(message.chat.id, "That is not an image! Please send me a picture.")
    if picture:
        announcement_id = await state.get_value("announcement_id")
        announcement = await message_service.update_message(announcement_id=announcement_id, picture=picture)
        text = "<pre>Here is your announcement:</pre>\n\n"
        question = "\n\n<pre>Do you want to send this announcement?</pre>"
        keyboard = await build_yes_no_keyboard(yes_text="Send", no_text="cancel",
                                               yes_action=AdminMenuAction.send_announcement,
                                               no_action=AdminMenuAction.select_group)
        message = await bot.send_photo(chat_id=message.chat.id, photo=announcement.picture,
                                     caption=text + announcement.text + question, reply_markup=keyboard)
    await state.update_data(message_id=message.message_id)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.skip_adding_picture))
async def show_send_announcement_dialogue(callback: CallbackQuery, state: FSMContext):
    await delete_messages_safely(chat_id=callback.message.chat.id, message_ids=[callback.message.message_id])
    announcement_id = await state.get_value("announcement_id")
    announcement = await message_service.get_message(announcement_id=announcement_id)
    text = "<pre>Here is your announcement:</pre>\n\n"
    question = "\n\n<pre>Do you want to send this announcement?</pre>"
    keyboard = await build_yes_no_keyboard(yes_text="Send", no_text="Cancel", yes_action=AdminMenuAction.send_announcement, no_action=AdminMenuAction.select_group)
    if announcement.picture:
        reply = await bot.send_photo(chat_id=callback.message.chat.id, photo=announcement.picture, caption=text + announcement.text + question, reply_markup=keyboard)
    else:
        reply = await bot.send_message(chat_id=callback.message.chat.id, text=text + announcement.text + question, reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id)

@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.send_announcement))
async def send_announcement(callback: CallbackQuery, state: FSMContext):
    announcement_id = await state.get_value("announcement_id")
    announcement = await message_service.get_message(announcement_id=announcement_id)
    logger.warning(f"Got ID {announcement_id} and announcement {announcement}")
    can_pin_announcements = await group_permission_service.check_permission(announcement.group_id, "can_pin_messages")

    if announcement.picture:
        result = await bot.send_photo(chat_id=announcement.group_id, message_thread_id=announcement.topic_id, photo=announcement.picture, caption=announcement.text)
        logger.warning(result)
    else:
        result = await bot.send_message(chat_id=announcement.group_id, message_thread_id=announcement.topic_id, text=announcement.text)
    if not result:
        failed_to_send_text = await t_for(key="admin_interactions.create_announcement.failed_to_send_announcement",
                                          user_id=callback.from_user.id)
        await callback.answer(failed_to_send_text)
        return

    announcement = await message_service.update_message(announcement_id=announcement.id, message_id=result.message_id, is_published=True)

    success_text = await t_for(key="admin_interactions.create_announcement.announcement_sent",
                               user_id=callback.from_user.id)
    pin_dialogue_text = await t_for(key="admin_interactions.create_announcement.pin.pin_dialogue",
                                    user_id=callback.from_user.id)
    await delete_messages_safely(callback.message.chat.id, [callback.message.message_id])
    if can_pin_announcements:
        await state.set_state(Announcement.confirming_pin)
        keyboard = await build_confirm_pin_keyboard(group_id=announcement.group_id,
                                                    announcement_id=announcement.message_id)
        await bot.send_message(chat_id=callback.message.chat.id,
                                  text=f"P{success_text}\n{pin_dialogue_text}",
                                  reply_markup=keyboard)
    else:
        group = await group_service.get_group(announcement.group_id)
        selected_group_dialogue_text = await t_for(key="admin_interactions.group_management.group_selected",
                                                   user_id=callback.from_user.id,
                                                   title=group.title)
        features = await group_service.get_features(announcement.group_id)
        keyboard = await build_main_features_keyboard(announcement.group_id, features)
        text = f"{success_text}\n\n{selected_group_dialogue_text}"

        await bot.send_message(chat_id=callback.message.chat.id,
                                  text=text,
                                  reply_markup=keyboard)
        await state.set_state(AdminPanel.managing_features)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.set_announcement_button_name))
async def show_setting_button_name_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await state.set_state(Announcement.setting_button_name)
    text = await t_for(key="admin_interactions.create_announcement.payment.button_name_dialogue",
                       user_id=callback.from_user.id)
    await edit_message_safely(callback.message, text=text)


@router.message(Announcement.setting_button_name, F.text)
async def set_announcement_button_name_and_show_callback_title_dialogue(message: Message, state: FSMContext):
    message_id = await state.get_value("message_id")
    await delete_messages_safely(message.chat.id, [message_id, message.message_id])

    if len(message.text) > 64:
        title_is_too_long_text = await t_for(key="admin_interactions.create_announcement.payment.title_too_long",
                                             user_id=message.from_user.id)
        reply = await bot.send_message(chat_id=message.chat.id, text=title_is_too_long_text)
    else:
        await state.set_state(Announcement.setting_callback_title)
        success_text = await t_for(key="admin_interactions.create_announcement.payment.button_name_added",
                                   user_id=message.from_user.id,
                                   name=message.text)
        event_name_dialogue_text = await t_for(key="admin_interactions.create_announcement.payment.event_name_dialogue",
                                               user_id=message.from_user.id)
        reply = await bot.send_message(chat_id=message.chat.id,
                                       text=f"{success_text}\n\n{event_name_dialogue_text}", )
    await state.update_data(message_id=reply.message_id, button_name=message.text)


# @router.message(Announcement.setting_callback_title, F.text)
# async def set_callback_title(message: Message, state: FSMContext):
#     group_id = await state.get_value("group_id")
#     announcement_id = await state.get_value("announcement_id")
#     message_id = await state.get_value("message_id")
#     button_name = await state.get_value("button_name")
#     await delete_messages_safely(message.chat.id, [message_id, message.message_id])
#     if len(message.text) > 64:
#         title_is_too_long_text = await t_for(key="admin_interactions.create_announcement.payment.title_too_long",
#                                              user_id=message.from_user.id)
#         reply = await bot.send_message(chat_id=message.chat.id, text=title_is_too_long_text)
#     else:
#         try:
#             await message_service.add_button_to_announcement(group_id=group_id, message_id=announcement_id,
#                                                              button_text=button_name, event_name=message.text, )
#             await state.set_state(Announcement.setting_reward_type)
#             keyboard = await build_reward_type_keyboard(announcement_id=announcement_id, group_id=group_id)
#             reward_dialogue_text = await t_for(key="admin_interactions.create_announcement.payment.reward_dialogue",
#                                                user_id=message.from_user.id)
#             reply = await bot.send_message(chat_id=message.chat.id, text=reward_dialogue_text,
#                                            reply_markup=keyboard)
#         except ValueError as e:
#             reply = await bot.send_message(chat_id=message.chat.id, text=e.args[0])
#     await state.update_data(message_id=reply.message_id)


# async def show_pin_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
#     can_pin_announcements = await group_permission_service.check_permission(callback_data.group_id, "can_pin_messages")
#     if not can_pin_announcements:
#         keyboard = await build_confirm_pin_keyboard(group_id=callback_data.group_id,
#                                                     announcement_id=callback_data.announcement_id)
#         pin_dialogue_text = await t_for(key="admin_interactions.create_announcement.pin.pin_dialogue",
#                                         user_id=callback.from_user.id)
#         await edit_message_safely(message=callback.message, text=pin_dialogue_text,
#                                   reply_markup=keyboard)
#         await state.set_state(Announcement.confirming_pin)
#     else:
#         group = await group_service.get_or_create_group(callback_data.group_id)
#         features = await group_service.get_features(callback_data.group_id)
#         keyboard = await build_main_features_keyboard(callback_data.group_id, features,
#                                                       callback.from_user.id == settings.ADMIN_TELEGRAM_ID)
#         success_text = await t_for(key="admin_interactions.create_announcement.announcement_sent",
#                                    user_id=callback.from_user.id)
#         group_features_dialogue = await t_for(key="admin_interactions.group_management.group_selected",
#                                               user_id=callback.from_user.id,
#                                               title=group.title)
#         await edit_message_safely(message=callback.message,
#                                   text=f"{success_text}\n\n{group_features_dialogue}",
#                                   reply_markup=keyboard)
#         await state.set_state(AdminPanel.managing_features)


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
