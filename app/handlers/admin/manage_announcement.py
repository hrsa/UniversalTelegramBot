from datetime import datetime

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger

from app.bot.core import bot
from app.config import settings
from app.db.session import async_session_maker
from app.schemas.callbacks import AdminCallback, AdminMenuAction
from app.schemas.states import Announcement
from app.helpers.admin_interactions import edit_message_safely, delete_messages_safely, build_skip_button, \
    build_reward_type_keyboard, \
    build_invitation_group_keyboard, build_announcement_mgmt_message, \
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
async def modify_button_name_and_show_callback_title_dialogue(message: Message, state: FSMContext):
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
        return await show_modify_thank_you_message_dialogue(callback, callback_data, state)

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
async def show_add_payment_product_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
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
async def show_modify_reward_type_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
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
            return await show_modify_thank_you_message_dialogue(callback, callback_data, state)
        text = "You've successfully chosen to reward participants with a message."
        keyboard = await build_skip_button(announcement_id=callback_data.announcement_id,
                                           group_id=callback_data.group_id,
                                           action=AdminMenuAction.manage_announcements,
                                           button_name="⬅️ Back")
    return await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.modify_thank_you_message))
async def show_modify_thank_you_message_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
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