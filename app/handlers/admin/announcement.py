from datetime import datetime
from typing import cast

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger

from app.bot.core import bot
from app.config import settings
from app.db.session import async_session_maker
from app.handlers.admin.admin_interactions import process_group_selection
from app.handlers.admin.states import AdminPanel, Announcement
from app.handlers.admin.callbacks import AdminCallback, AdminMenuAction
from app.helpers.admin_interactions import edit_message_safely, build_confirm_announcement_keyboard, \
    build_confirm_pin_keyboard, delete_messages_safely, build_skip_button, build_reward_type_keyboard, \
    build_invitation_group_keyboard, build_main_features_keyboard, build_announcement_mgmt_message, \
    build_announcement_delete_confirmation, build_remove_payment_keyboard, build_participants_list
from app.services.admin import AdminService
from app.services.group import GroupService
from app.services.group_permission import GroupPermissionService
from app.services.message import MessageService
from app.services.reward import RewardService
from app.services.stripe_payment import StripePaymentService

router = Router()
group_permission_service = GroupPermissionService(async_session_maker)
group_service = GroupService(async_session_maker)
admin_service = AdminService(async_session_maker, group_service, group_permission_service)
message_service = MessageService(async_session_maker)
reward_service = RewardService(async_session_maker, message_service)
stripe_payment_service = StripePaymentService()


@router.callback_query(AdminPanel.managing_features,
                       AdminCallback.filter(F.action == AdminMenuAction.make_announcement))
async def set_announcement_text(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    group = await group_service.get_group(callback_data.group_id)
    await state.update_data(group_id=callback_data.group_id, message_id=callback.message.message_id)
    await state.set_state(Announcement.creating_announcement)
    await edit_message_safely(message=callback.message,
                              text=f"Please enter the <b>text</b> of the announcement for {group.title}.")


@router.message(Announcement.creating_announcement, F.text)
async def show_confirmation_dialogue(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    message_id = await state.get_value("message_id")
    await state.update_data(announcement_text=message.text)
    await delete_messages_safely(message.chat.id, [message.message_id, message_id])

    keyboard = await build_confirm_announcement_keyboard(group_id)
    confirmation_text = f"Here is the announcement i'll send:\n\n{message.text}"

    await bot.send_message(message.chat.id, text=confirmation_text, reply_markup=keyboard)
    await state.set_state(Announcement.confirming_announcement)


@router.callback_query(Announcement.confirming_announcement,
                       AdminCallback.filter((F.action == AdminMenuAction.confirm_announcement) & F.level == 2))
async def send_announcement(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    group_id = await state.get_value("group_id")

    can_add_payments = callback.from_user.id == settings.ADMIN_TELEGRAM_ID and await group_service.feature_is_active(
        group_id, "allow_payments")
    can_pin_announcements = await group_permission_service.check_permission(group_id, "can_pin_messages")

    announcement_text = await state.get_value("announcement_text")
    announcement = await bot.send_message(chat_id=group_id, text=announcement_text)
    if not announcement:
        await callback.answer("Failed to send announcement. Please try again later.")
        return
    saved_announcement = await message_service.create_message(group_id=group_id, message_id=announcement.message_id,
                                                              text=announcement_text, is_watched=True, is_pinned=False)
    if can_add_payments:
        await state.set_state(Announcement.adding_payment_product)
        await state.update_data(message_id=callback.message.message_id, announcement_id=saved_announcement.message_id,
                                group_id=group_id)
        text = f"Would you like to add a payment button to this announcement?\nIf yes - please reply with the Stripe product ID you'd like to attach."
        keyboard = await build_skip_button(announcement_id=saved_announcement.message_id,
                                           group_id=saved_announcement.group_id, button_name="Don't add payment",
                                           action=AdminMenuAction.skip_to_pin_announcement)
        await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)
    else:
        if can_pin_announcements:
            await state.set_state(Announcement.confirming_pin)
            keyboard = await build_confirm_pin_keyboard(group_id=group_id,
                                                        announcement_id=saved_announcement.message_id)
            await edit_message_safely(message=callback.message,
                                      text=f"Announcement sent successfully!\nDo you want me to pin it?",
                                      reply_markup=keyboard)
        else:
            group = await group_service.get_group(group_id)
            features = await group_service.get_features(group_id)
            keyboard = await build_main_features_keyboard(group_id, features,
                                                          callback.from_user.id == settings.ADMIN_TELEGRAM_ID)
            text = f"Announcement sent successfully!\n\nSelected group: {group.title}. What do you want to do with it?"

            await edit_message_safely(message=callback.message,
                                      text=text,
                                      reply_markup=keyboard)
            await state.set_state(AdminPanel.managing_features)


@router.message(Announcement.adding_payment_product, F.text)
async def add_main_payment_product(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    message_id = await state.get_value("message_id")
    await delete_messages_safely(message.chat.id, [message_id, message.message_id])
    try:
        stripe_product = await stripe_payment_service.get_product(message.text)
        await message_service.set_stripe_product_id(group_id=group_id, message_id=announcement_id,
                                                    stripe_product_id=stripe_product.id)

        await state.set_state(Announcement.adding_early_bird_payment_product)
        keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                           action=AdminMenuAction.set_payment_expiration_date,
                                           button_name="Don't add early bird payment")
        reply = await bot.send_message(chat_id=message.chat.id,
                                       text=f"Product '{stripe_product.name}' added successfully!\nDo you want me to add an early bird payment product as well?\nPlease reply with a stripe product id.",
                                       reply_markup=keyboard)
    except Exception as e:
        keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                           action=AdminMenuAction.skip_to_pin_announcement,
                                           button_name="Don't add payment")
        reply = await bot.send_message(chat_id=message.chat.id,
                                       text=f"Failed to add payment product: {e}.\n\nPlease check again and enter another product id.",
                                       reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id)


@router.message(Announcement.adding_early_bird_payment_product, F.text)
@router.message(Announcement.modifying_early_bird_payment_product, F.text)
async def add_early_bird_payment_product(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    message_id = await state.get_value("message_id")
    await delete_messages_safely(message.chat.id, [message_id, message.message_id])
    if await state.get_state() == Announcement.adding_early_bird_payment_product:
        try:
            stripe_product = await stripe_payment_service.get_product(message.text)
            await message_service.set_early_bird_stripe_product_id(group_id=group_id, message_id=announcement_id,
                                                                   early_bird_stripe_product_id=stripe_product.id)
            keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                               action=AdminMenuAction.set_participants_limit,
                                               button_name="Don't add expiration date")

            await state.set_state(Announcement.setting_payment_expiration_date)
            reply = await bot.send_message(chat_id=message.chat.id,
                                           text=f"Early bird '{stripe_product.name}' added successfully!\nDo you want to add an expiration date?\n\nPlease enter expiration date in format YYYY/MM/DD",
                                           reply_markup=keyboard)
        except Exception as e:
            keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                               action=AdminMenuAction.set_payment_expiration_date,
                                               button_name="Don't add early bird payment")
            reply = await bot.send_message(chat_id=message.chat.id,
                                           text=f"Failed to add early bird payment product: {e}.\n\nPlease check again and enter another product id.",
                                           reply_markup=keyboard)
    else:
        keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                           action=AdminMenuAction.manage_announcements,
                                           button_name="⬅️ Back")
        try:
            stripe_product = await stripe_payment_service.get_product(message.text)
            await message_service.set_early_bird_stripe_product_id(group_id=group_id, message_id=announcement_id,
                                                                   early_bird_stripe_product_id=stripe_product.id)
            reply = await bot.send_message(chat_id=message.chat.id,
                                           text=f"Early bird '{stripe_product.name}' added successfully!",
                                           reply_markup=keyboard)
        except Exception as e:
            reply = await bot.send_message(chat_id=message.chat.id,
                                           text=f"Failed to add early bird payment product: {e}.\n\nPlease check again and enter another product id.",
                                           reply_markup=keyboard)

    await state.update_data(message_id=reply.message_id)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.set_payment_expiration_date))
async def show_expiration_date_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await  state.set_state(Announcement.setting_payment_expiration_date)
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    text = "Do you want to add an expiration date?\n\nPlease enter expiration date in format YYYY/MM/DD"
    keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                       action=AdminMenuAction.set_participants_limit,
                                       button_name="Don't add expiration date")
    await edit_message_safely(callback.message, text=text, reply_markup=keyboard)


@router.message(Announcement.setting_payment_expiration_date, F.text)
async def add_expiration_date(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    message_id = await state.get_value("message_id")
    await delete_messages_safely(message.chat.id, [message_id, message.message_id])
    expiration_date = message.text
    try:
        await message_service.set_expiration_date(group_id=group_id, message_id=announcement_id,
                                                  expiration_date=expiration_date)
        await state.set_state(Announcement.setting_participants_limit)
        keyboard = await build_skip_button(group_id=group_id, announcement_id=announcement_id,
                                           action=AdminMenuAction.set_announcement_button_name,
                                           button_name="Don't add participants limit")
        reply = await bot.send_message(chat_id=message.chat.id,
                                       text="Expiration date added successfully! Do you want to limit the number of participants?",
                                       reply_markup=keyboard)
    except ValueError as e:
        keyboard = await build_skip_button(group_id=group_id, announcement_id=announcement_id,
                                           action=AdminMenuAction.set_participants_limit,
                                           button_name="Don't add expiration date")
        reply = await bot.send_message(chat_id=message.chat.id, text=e.args[0], reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.set_participants_limit))
async def show_participants_limit_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await state.set_state(Announcement.setting_participants_limit)
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    text = "Do you want to limit the number of participants?"
    keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                       action=AdminMenuAction.set_announcement_button_name,
                                       button_name="Don't add participants limit")
    await edit_message_safely(callback.message, text=text, reply_markup=keyboard)


@router.message(Announcement.setting_participants_limit, F.text)
async def add_participants_limit(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    message_id = await state.get_value("message_id")
    await delete_messages_safely(message.chat.id, [message_id, message.message_id])

    try:
        participants_limit = int(message.text)
        await message_service.set_participants_limit(group_id=group_id, message_id=announcement_id,
                                                     participants_limit=participants_limit)
        await state.set_state(Announcement.setting_button_name)
        reply = await bot.send_message(chat_id=message.chat.id,
                                       text=f"You event is limited to {participants_limit} participants!\nFinally, let's choose a name for the button on the announcement. Please reply with the button name.")
    except ValueError as e:
        keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                           action=AdminMenuAction.set_announcement_button_name,
                                           button_name="Don't add participants limit")
        reply = await bot.send_message(chat_id=message.chat.id, text=e.args[0], reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.set_announcement_button_name))
async def show_setting_button_name_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await state.set_state(Announcement.setting_button_name)
    text = "Let's choose a name for the button on the announcement. Please reply with the button name."
    await edit_message_safely(callback.message, text=text)


@router.message(Announcement.setting_button_name, F.text)
async def set_announcement_button_name(message: Message, state: FSMContext):
    message_id = await state.get_value("message_id")
    await delete_messages_safely(message.chat.id, [message_id, message.message_id])

    if len(message.text) > 64:
        reply = await bot.send_message(chat_id=message.chat.id, text="This title is too long!")
    else:
        await state.set_state(Announcement.setting_callback_title)
        reply = await bot.send_message(chat_id=message.chat.id,
                                       text=f"Button name will be set to <b>\"{message.text}\"</b>.\n"
                                            f"Please write the event name for your announcement.")
    await state.update_data(message_id=reply.message_id, button_name=message.text)


@router.message(Announcement.setting_callback_title, F.text)
async def set_callback_title(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    message_id = await state.get_value("message_id")
    button_name = await state.get_value("button_name")
    await delete_messages_safely(message.chat.id, [message_id, message.message_id])
    if len(message.text) > 64:
        reply = await bot.send_message(chat_id=message.chat.id, text="This title is too long!")
    else:
        try:
            await message_service.add_button_to_announcement(group_id=group_id, message_id=announcement_id,
                                                             button_text=button_name, event_name=message.text, )
            await state.set_state(Announcement.setting_reward_type)
            keyboard = await build_reward_type_keyboard(announcement_id=announcement_id, group_id=group_id)
            reply = await bot.send_message(chat_id=message.chat.id, text="Which reward would you like to add?",
                                           reply_markup=keyboard)
        except ValueError as e:
            reply = await bot.send_message(chat_id=message.chat.id, text=e.args[0])
    await state.update_data(message_id=reply.message_id)


@router.callback_query(Announcement.setting_reward_type,
                       AdminCallback.filter(F.action == AdminMenuAction.set_reward_type))
async def set_reward_type(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await state.update_data(reward_type=callback_data.reward_type, message_id=callback.message.message_id)
    await state.set_state(Announcement.setting_thank_you_message)

    text = F"Reward type set to {callback_data.reward_type.capitalize()}.\n\n"
    if callback_data.reward_type == "invite":
        text += ("You've chosen to reward participants with an invitation to a group.\n"
                 "<b>If you haven't done this yet, please <u>create the group NOW and promote me to administrator</u>!</b>\n\n")

    text += (F"Please enter the thank you message you'd like to send to the participants.\n\n"
             F"Add <b>%USERNAME%</b> if you want to include the username in the message.")
    await edit_message_safely(callback.message, text=text)


@router.message(Announcement.setting_thank_you_message, F.text)
async def set_thank_you_message(message: Message, state: FSMContext):
    reward_type = await state.get_value("reward_type")
    message_id = await state.get_value("message_id")
    group_id = await state.get_value("group_id")
    await delete_messages_safely(message.chat.id, [message.message_id, message_id])
    if reward_type == "invite":
        main_group_id = await state.get_value("group_id")
        await state.update_data(thank_you_message=message.text)
        await state.set_state(Announcement.setting_invitation_group)
        groups = await admin_service.get_my_groups_for_invitation(message.from_user.id, main_group_id)
        keyboard = await build_invitation_group_keyboard(groups)
        text = (F"Thank you message set to:\n\n"
                F"{message.text}\n\n"
                F"Please choose the group where you'd like to invite the participants.")
        await bot.send_message(chat_id=message.chat.id, text=text, reply_markup=keyboard)
    else:
        announcement_id = await state.get_value("announcement_id")
        announcement = await message_service.get_message(group_id=group_id, message_id=announcement_id)
        reward = await reward_service.create_reward(announcement_id=announcement.id, reward_type=reward_type,
                                                    thank_you_message=message.text)
        can_pin_announcements = await group_permission_service.check_permission(group_id, "can_pin_messages")
        if can_pin_announcements:
            await state.set_state(Announcement.confirming_pin)
            keyboard = await build_confirm_pin_keyboard(group_id=group_id, announcement_id=announcement_id)
            await bot.send_message(chat_id=message.chat.id,
                                   text=f"Announcement created successfully!\n\nDo you want me to pin it?",
                                   reply_markup=keyboard)
        else:
            group = await group_service.get_group(group_id)
            features = await group_service.get_features(group_id)
            keyboard = await build_main_features_keyboard(group_id, features,
                                                          message.from_user.id == settings.ADMIN_TELEGRAM_ID)
            text = f"Announcement sent successfully!\n\nSelected group: {group.title}. What do you want to do with it?"

            await bot.send_message(chat_id=message.chat.id, text=text, reply_markup=keyboard)
            await state.set_state(AdminPanel.managing_features)


@router.callback_query(Announcement.setting_invitation_group,
                       AdminCallback.filter(F.action == AdminMenuAction.set_invitation_group))
async def set_invitation_group(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    reward_type = await state.get_value("reward_type")
    thank_you_message = await state.get_value("thank_you_message")
    announcement_id = await state.get_value("announcement_id")
    group_id = await state.get_value("group_id")
    reward_group = await group_service.get_group(callback_data.group_id)
    announcement = await message_service.get_message(group_id=group_id, message_id=announcement_id)
    await reward_service.create_reward(announcement_id=announcement.id, reward_type=reward_type,
                                       thank_you_message=thank_you_message, group_id=callback_data.group_id)
    can_pin_announcements = await group_permission_service.check_permission(group_id, "can_pin_messages")
    if can_pin_announcements:
        await state.set_state(Announcement.confirming_pin)
        keyboard = await build_confirm_pin_keyboard(group_id=group_id, announcement_id=announcement_id)
        text = f"A reward to join group {reward_group.title} has been created successfully!\n\nDo you want me to pin the announcement?"
        await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)
    else:
        group = await group_service.get_group(group_id)
        features = await group_service.get_features(group_id)
        keyboard = await build_main_features_keyboard(group_id, features,
                                                      callback.from_user.id == settings.ADMIN_TELEGRAM_ID)
        text = f"Announcement sent successfully!\n\nSelected group: {group.title}. What do you want to do with it?"

        await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)
        await state.set_state(AdminPanel.managing_features)


@router.callback_query(Announcement.adding_payment_product,
                       AdminCallback.filter(F.action == AdminMenuAction.skip_to_pin_announcement))
@router.callback_query(Announcement.setting_participants_limit,
                       AdminCallback.filter(F.action == AdminMenuAction.skip_to_pin_announcement))
async def skip_to_pin_announcement(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    can_pin_announcements = await group_permission_service.check_permission(callback_data.group_id, "can_pin_messages")
    if not can_pin_announcements:
        keyboard = await build_confirm_pin_keyboard(group_id=callback_data.group_id,
                                                    announcement_id=callback_data.announcement_id)
        await edit_message_safely(message=callback.message, text=f"Do you want me to pin the announcement?",
                                  reply_markup=keyboard)
        await state.set_state(Announcement.confirming_pin)
    else:
        group = await group_service.get_or_create_group(callback_data.group_id)
        features = await group_service.get_features(callback_data.group_id)
        keyboard = await build_main_features_keyboard(callback_data.group_id, features,
                                                      callback.from_user.id == settings.ADMIN_TELEGRAM_ID)
        text = f"Announcement sent successfully!\n\nSelected group: {group.title}. What do you want to do with it?"

        await edit_message_safely(message=callback.message,
                                  text=text,
                                  reply_markup=keyboard)
        await state.set_state(AdminPanel.managing_features)


@router.callback_query(Announcement.confirming_pin,
                       AdminCallback.filter((F.action == AdminMenuAction.confirm_pin) & F.level == 2))
async def pin_announcement(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await bot.pin_chat_message(chat_id=callback_data.group_id, message_id=callback_data.announcement_id)
    await message_service.pin_message(group_id=callback_data.group_id, message_id=callback_data.announcement_id)
    await callback.answer("Pinned successfully!")

    await state.set_state(AdminPanel.managing_features)
    await process_group_selection(callback, callback_data, state)


@router.callback_query(Announcement.managing_announcements,
                       AdminCallback.filter(F.action == AdminMenuAction.delete_announcement))
async def confirm_announcement_deletion(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    announcement = await message_service.get_message(group_id=callback_data.group_id,
                                                     message_id=callback_data.announcement_id, with_payments=True,
                                                     with_reward_groups=True, with_rewards=True)
    text, keyboard = await build_announcement_delete_confirmation(announcement, callback_data.announcement_offset)
    await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)


@router.callback_query(Announcement.managing_announcements,
                       AdminCallback.filter(F.action == AdminMenuAction.confirm_delete_announcement))
async def delete_announcement(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await delete_messages_safely(chat_id=callback_data.group_id, message_ids=[callback_data.announcement_id])
    await message_service.delete_message(group_id=callback_data.group_id, message_id=callback_data.announcement_id)
    await callback.answer("Announcement deleted successfully!")
    await manage_announcements(callback, callback_data, state)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.manage_announcements))
async def manage_announcements(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await state.set_state(Announcement.managing_announcements)
    offset = callback_data.announcement_offset if callback_data.announcement_offset is not None else 0
    limit = 1
    can_add_payments = callback.from_user.id == settings.ADMIN_TELEGRAM_ID and await group_service.feature_is_active(
        callback_data.group_id, "allow_payments")
    can_pin_announcements = await group_permission_service.check_permission(callback_data.group_id, "can_pin_messages")

    announcements, count = await group_service.get_group_announcements(group_id=callback_data.group_id, offset=offset,
                                                                       limit=limit,
                                                                       with_payments=True, with_reward_groups=True,
                                                                       with_rewards=True)
    text, keyboard = await build_announcement_mgmt_message(announcement=announcements[0] if announcements else None, group_id=callback_data.group_id, count=count, offset=offset,
                                                           can_add_payments=can_add_payments, can_pin_announcements=can_pin_announcements)
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
            await callback.answer("Un-pinned successfully!")
        else:
            await bot.pin_chat_message(chat_id=callback_data.group_id, message_id=callback_data.announcement_id)
            await message_service.pin_message(group_id=callback_data.group_id, message_id=callback_data.announcement_id)
            await callback.answer("Pinned successfully!")

    await manage_announcements(callback, callback_data, state)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.modify_expiration_date))
async def show_modify_expiration_date_dialogue(callback: CallbackQuery, callback_data: AdminCallback,
                                               state: FSMContext):
    await  state.set_state(Announcement.modifying_expiration_date)
    announcement = await message_service.get_message(group_id=callback_data.group_id,
                                                     message_id=callback_data.announcement_id)
    await state.update_data(message_id=callback.message.message_id, announcement_id=callback_data.announcement_id,
                            group_id=callback_data.group_id)
    text = ""
    if announcement.payment_expires_at is not None and isinstance(announcement.payment_expires_at, datetime):
        current_expiration_date = announcement.payment_expires_at.strftime("%d %B %Y")
        text += f"Announcement expires on <b>{current_expiration_date}</b>\n\n"

    text += "Please enter new expiration date in format <b>YYYY/MM/DD</b>"
    keyboard = await build_skip_button(announcement_id=callback_data.announcement_id, group_id=callback_data.group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name="⬅️ Back")
    await edit_message_safely(callback.message, text=text, reply_markup=keyboard)


@router.message(Announcement.modifying_expiration_date, F.text)
async def modify_expiration_date(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    message_id = await state.get_value("message_id")
    await delete_messages_safely(message.chat.id, [message_id, message.message_id])
    expiration_date = message.text
    keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name="⬅️ Back")
    try:
        await message_service.set_expiration_date(group_id=group_id, message_id=announcement_id,
                                                  expiration_date=expiration_date)
        reply = await bot.send_message(chat_id=message.chat.id,
                                       text="Expiration date modified successfully!",
                                       reply_markup=keyboard)
    except ValueError as e:
        reply = await bot.send_message(chat_id=message.chat.id, text=e.args[0], reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.modify_max_participants))
async def show_modify_participants_limit_dialogue(callback: CallbackQuery, callback_data: AdminCallback,
                                                  state: FSMContext):
    await state.set_state(Announcement.modifying_max_participants)
    group_id = callback_data.group_id
    announcement_id = callback_data.announcement_id
    announcement = await message_service.get_message(group_id=callback_data.group_id,
                                                     message_id=callback_data.announcement_id)

    text = (f"Current maximum number of participants: {announcement.participants_limit}.\n"
            f"Please reply with the new number.")
    keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name="⬅️ Back")
    await state.update_data(message_id=callback.message.message_id, announcement_id=announcement_id, group_id=group_id)
    await edit_message_safely(callback.message, text=text, reply_markup=keyboard)


@router.message(Announcement.modifying_max_participants, F.text)
async def modify_participants_limit(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    message_id = await state.get_value("message_id")
    await delete_messages_safely(message.chat.id, [message_id, message.message_id])
    keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name="⬅️ Back")
    try:
        participants_limit = int(message.text)
        await message_service.set_participants_limit(group_id=group_id, message_id=announcement_id,
                                                     participants_limit=participants_limit)
        reply = await bot.send_message(chat_id=message.chat.id,
                                       text=f"You announcement is now limited to {participants_limit} participants!",
                                       reply_markup=keyboard)
    except ValueError as e:
        reply = await bot.send_message(chat_id=message.chat.id, text=e.args[0], reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.modify_callback_button_title))
async def show_modify_callback_button_title_dialogue(callback: CallbackQuery, callback_data: AdminCallback,
                                                     state: FSMContext):
    await state.set_state(Announcement.modifying_button_name)
    text = f"Please write the new button name for your announcement.\nUse 64 characters max."
    keyboard = await build_skip_button(announcement_id=callback_data.announcement_id, group_id=callback_data.group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name="⬅️ Back")
    await state.update_data(message_id=callback.message.message_id, announcement_id=callback_data.announcement_id,
                            group_id=callback_data.group_id)
    await edit_message_safely(callback.message, text=text, reply_markup=keyboard)


@router.message(Announcement.modifying_button_name, F.text)
async def modify_button_name(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    message_id = await state.get_value("message_id")
    await delete_messages_safely(message.chat.id, [message_id, message.message_id])
    keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name="⬅️ Back")
    if len(message.text) > 64:
        reply = await bot.send_message(chat_id=message.chat.id, text="This title is too long!", reply_markup=keyboard)
    else:
        await state.set_state(Announcement.modifying_callback_title)
        reply = await bot.send_message(chat_id=message.chat.id,
                                       text=f"Button name will be set to <b>\"{message.text}\"</b>.\n"
                                            f"Please write the event name for your announcement.\n"
                                            f"You can reply with <b>\"skip\"</b> to skip this step and set it to {message.text}, too.",
                                       reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id, button_name=message.text)


@router.message(Announcement.modifying_callback_title, F.text)
async def modify_callback_title(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    message_id = await state.get_value("message_id")
    button_name = await state.get_value("button_name")
    callback_title = message.text if message.text != "skip" else button_name
    await delete_messages_safely(message.chat.id, [message_id, message.message_id])
    keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name="⬅️ Back")
    if len(callback_title) > 64:
        reply = await bot.send_message(chat_id=message.chat.id, text="This title is too long!", reply_markup=keyboard)
    else:
        try:
            await message_service.add_button_to_announcement(group_id=group_id, message_id=announcement_id,
                                                             button_text=button_name,
                                                             event_name=callback_title)
            reply = await bot.send_message(chat_id=message.chat.id,
                                           text=f"Button \"{button_name}\" is successfully updated to <b>\"{callback_title}\"</b> event!",
                                           reply_markup=keyboard)
        except ValueError as e:
            reply = await bot.send_message(chat_id=message.chat.id, text=e.args[0], reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.modify_invitation_group))
async def show_modify_invite_group_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    group_id = callback_data.group_id
    groups = await admin_service.get_my_groups_for_invitation(callback.from_user.id, group_id)
    keyboard = await build_invitation_group_keyboard(groups=groups, modify=True)
    text = f"Please choose the group where you'd like to invite the participants."

    await state.update_data(announcement_id=callback_data.announcement_id, group_id=callback_data.group_id)
    await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.set_new_invitation_group))
async def modify_invite_group_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    reward_group = await group_service.get_group(callback_data.group_id)
    announcement = await message_service.get_message(group_id=group_id, message_id=announcement_id)
    reward = await reward_service.update_reward(announcement_id=announcement.id, reward_type="invite",
                                                group_id=callback_data.group_id)
    if not reward.thank_you:
        return await modify_thank_you_message_dialogue(callback, callback_data, state)

    keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name="⬅️ Back")
    text = f"Success!\nNow the participants will get an invitation to {reward_group.title}."
    return await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.remove_payment_product))
@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.remove_early_bird_payment_product))
async def show_remove_payment_product_dialogue(callback: CallbackQuery, callback_data: AdminCallback,
                                               state: FSMContext):
    await state.update_data(announcement_id=callback_data.announcement_id, group_id=callback_data.group_id)
    announcement = await message_service.get_message(group_id=callback_data.group_id,
                                                     message_id=callback_data.announcement_id)
    if callback_data.action == AdminMenuAction.remove_payment_product:
        text = (f"Are you sure you want to remove the payment?"
                f"\nThat will delete:"
                f"\n\n- main payment - {announcement.stripe_product_id}")
        if announcement.early_bird_stripe_product_id:
            text += f"\n- early bird payment - {announcement.early_bird_stripe_product_id}"
        if announcement.payment_expires_at and isinstance(announcement.payment_expires_at, datetime):
            text += f"\n- expiration date - {announcement.payment_expires_at.strftime("%d %B %Y")}"
        if announcement.participants_limit:
            text += f"\n- participants limit - {announcement.participants_limit} participants"
        text += f"\n- the interactive button"
        keyboard = await build_remove_payment_keyboard(announcement_id=announcement.message_id,
                                                       group_id=callback_data.group_id, early_bird_only=False)
    else:
        text = f"Are you sure you want to remove the early bird payment - {announcement.early_bird_stripe_product_id}?"
        keyboard = await build_remove_payment_keyboard(announcement_id=announcement.message_id,
                                                       group_id=callback_data.group_id, early_bird_only=True)
    await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.confirm_remove_payment_product))
@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.confirm_remove_early_bird_payment_product))
async def remove_payment_product(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    keyboard = await build_skip_button(announcement_id=callback_data.announcement_id, group_id=callback_data.group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name="⬅️ Back")
    if callback_data.action == AdminMenuAction.confirm_remove_payment_product:
        try:
            await message_service.remove_payment_product(group_id=callback_data.group_id,
                                                         message_id=callback_data.announcement_id)
            await message_service.remove_button_from_announcement(group_id=callback_data.group_id,
                                                                  message_id=callback_data.announcement_id)
            await edit_message_safely(message=callback.message, text="Payment successfully removed!",
                                      reply_markup=keyboard)
        except Exception as e:
            await edit_message_safely(message=callback.message, text=f"Failed to remove payment.\n{e}.",
                                      reply_markup=keyboard)
    else:
        try:
            await message_service.remove_early_bird_payment_product(group_id=callback_data.group_id,
                                                                    message_id=callback_data.announcement_id)
            await edit_message_safely(message=callback.message, text="Early bird payment successfully removed!",
                                      reply_markup=keyboard)
        except Exception as e:
            await edit_message_safely(message=callback.message, text=f"Failed to remove early bird payment.\n{e}.",
                                      reply_markup=keyboard)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.add_payment_product))
async def add_payment_product_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await state.set_state(Announcement.adding_payment_product)
    await state.update_data(message_id=callback.message.message_id, announcement_id=callback_data.announcement_id,
                            group_id=callback_data.group_id)
    text = f"Please reply with the Stripe product ID you'd like to attach."
    keyboard = await build_skip_button(announcement_id=callback_data.announcement_id, group_id=callback_data.group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name="⬅️ Back")
    await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.modify_early_bird_payment_product))
async def modify_early_bird_payment_product_dialogue(callback: CallbackQuery, callback_data: AdminCallback,
                                                     state: FSMContext):
    await state.set_state(Announcement.modifying_early_bird_payment_product)
    keyboard = await build_skip_button(announcement_id=callback_data.announcement_id, group_id=callback_data.group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name="⬅️ Back")
    await edit_message_safely(message=callback.message, text="Please reply with the new Stripe product ID.",
                              reply_markup=keyboard)
    await state.update_data(message_id=callback.message.message_id, announcement_id=callback_data.announcement_id,
                            group_id=callback_data.group_id)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.modify_reward_type))
async def modify_reward_type_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await state.set_state(Announcement.modifying_reward_type)
    keyboard = await build_reward_type_keyboard(announcement_id=callback_data.announcement_id,
                                                group_id=callback_data.group_id, modify=True)
    await edit_message_safely(message=callback.message, text="Please choose the reward type.", reply_markup=keyboard)


@router.callback_query(Announcement.modifying_reward_type,
                       AdminCallback.filter(F.action == AdminMenuAction.set_reward_type))
async def modify_reward_type(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await state.update_data(message_id=callback.message.message_id, announcement_id=callback_data.announcement_id,
                            group_id=callback_data.group_id)
    if callback_data.reward_type == "invite":
        text = (f"You've chosen to reward participants with an invitation to a group. Please select it below.\n"
                f"<b>If you can't find the group, please <u>add me and promote me to administrator</u>!</b>")
        main_group_id = await state.get_value("group_id")
        groups = await admin_service.get_my_groups_for_invitation(callback.from_user.id, main_group_id)
        keyboard = await build_invitation_group_keyboard(groups, modify=True)
    else:
        announcement = await message_service.get_message(group_id=callback_data.group_id,
                                                         message_id=callback_data.announcement_id)
        reward = await reward_service.update_reward(announcement_id=announcement.id, reward_type="message")
        if not reward.thank_you:
            return await modify_thank_you_message_dialogue(callback, callback_data, state)
        text = "You've successfully chosen to reward participants with a message."
        keyboard = await build_skip_button(announcement_id=callback_data.announcement_id,
                                           group_id=callback_data.group_id,
                                           action=AdminMenuAction.manage_announcements,
                                           button_name="⬅️ Back")
    return await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.modify_thank_you_message))
async def modify_thank_you_message_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await state.set_state(Announcement.modifying_thank_you_message)
    await state.update_data(message_id=callback.message.message_id)
    if callback_data.announcement_id:
        await state.update_data(announcement_id=callback_data.announcement_id)
    keyboard = await build_skip_button(announcement_id=callback_data.announcement_id, group_id=callback_data.group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name="⬅️ Back")
    text = (F"Please enter the thank you message you'd like to send to the participants.\n\n"
            F"Add <b>%USERNAME%</b> if you want to include the username in the message.")
    await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)


@router.message(Announcement.modifying_thank_you_message, F.text)
async def modify_thank_you_message(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    message_id = await state.get_value("message_id")
    await delete_messages_safely(message.chat.id, [message.message_id, message_id])
    keyboard = await build_skip_button(announcement_id=announcement_id,
                                       group_id=group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name="⬅️ Back")
    try:
        announcement = await message_service.get_message(group_id=group_id,
                                                         message_id=announcement_id)
        await reward_service.update_reward(announcement_id=announcement.id, thank_you_message=message.text)

        text = (F"Thank you message updated successfully!\n\n"
                F"New thank you message: <b>{message.text}</b>")
    except Exception as e:
        text = f"Failed to update thank you message.\n{e}"

    reply = await bot.send_message(chat_id=message.chat.id, text=text, reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id)

@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.get_announcement_participants))
async def get_announcement_participants(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    payments = await message_service.get_participants(message_id=callback_data.announcement_id, group_id=callback_data.group_id)
    text = await build_participants_list(payments)
    keyboard = await build_skip_button(announcement_id=callback_data.announcement_id,
                                       group_id=callback_data.group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name="⬅️ Back")
    await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)