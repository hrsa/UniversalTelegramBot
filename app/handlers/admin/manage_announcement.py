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
    build_announcement_delete_confirmation, build_remove_payment_keyboard, build_participants_list, \
    build_confirm_ai_vs_human_announcement_keyboard, build_modify_ai_vs_human_announcement_keyboard
from app.services.admin import AdminService
from app.services.ai import AIService
from app.services.group import GroupService
from app.services.group_permission import GroupPermissionService
from app.services.message import MessageService
from app.services.reward import RewardService
from app.services.stripe_payment import StripePaymentService
from app.services.translation import t_for

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
                       AdminCallback.filter(F.action == AdminMenuAction.rewrite_announcement))
async def rewrite_announcement(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await callback.answer("🤖 Thinking... 🤖")
    announcement = await message_service.get_message(group_id=callback_data.group_id,
                                                     message_id=callback_data.announcement_id, with_payments=True,
                                                     with_reward_groups=True, with_rewards=True)
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
    await bot.edit_message_text(chat_id=callback_data.group_id, message_id=callback_data.announcement_id, text=rewritten_text)
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
    can_add_payments = callback.from_user.id == settings.ADMIN_TELEGRAM_ID and await group_service.feature_is_active(
        callback_data.group_id, "allow_payments")
    can_pin_announcements = await group_permission_service.check_permission(callback_data.group_id, "can_pin_messages")

    announcements, count = await group_service.get_group_announcements(group_id=callback_data.group_id, offset=offset,
                                                                       limit=limit,
                                                                       with_payments=True, with_reward_groups=True,
                                                                       with_rewards=True)
    text, keyboard = await build_announcement_mgmt_message(announcement=announcements[0] if announcements else None,
                                                           group_id=callback_data.group_id, count=count, offset=offset,
                                                           can_add_payments=can_add_payments,
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
        text += await t_for(key="admin_interactions.manage_announcement.expires_on", user_id=callback.from_user.id,
                            expires_on=current_expiration_date)
        text += "\n\n"

    text += await t_for(key="admin_interactions.manage_announcement.enter_new_expiration_date",
                        user_id=callback.from_user.id)
    back_text = await t_for(key="admin_interactions.buttons.back", user_id=callback.from_user.id)

    keyboard = await build_skip_button(announcement_id=callback_data.announcement_id, group_id=callback_data.group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name=back_text)
    await edit_message_safely(callback.message, text=text, reply_markup=keyboard)


@router.message(Announcement.modifying_expiration_date, F.text)
async def modify_expiration_date(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    message_id = await state.get_value("message_id")
    await delete_messages_safely(message.chat.id, [message_id, message.message_id])
    expiration_date = message.text
    back_text = await t_for(key="admin_interactions.buttons.back", user_id=message.from_user.id)
    keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name=back_text)
    try:
        await message_service.set_expiration_date(group_id=group_id, message_id=announcement_id,
                                                  expiration_date=expiration_date)
        success_text = await t_for(key="admin_interactions.manage_announcement.expiration_date_modified",
                                   user_id=message.from_user.id)
        reply = await bot.send_message(chat_id=message.chat.id,
                                       text=success_text,
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

    modify_participants_limit_dialogue = await t_for(
        key="admin_interactions.manage_announcement.modify_participants_limit_dialogue",
        user_id=callback.from_user.id,
        current_limit=announcement.participants_limit if announcement.participants_limit else "No limit")
    back_button_text = await t_for(key="admin_interactions.buttons.back", user_id=callback.from_user.id,
                                   default_locale=callback.from_user.language_code)
    keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name=back_button_text)
    await state.update_data(message_id=callback.message.message_id, announcement_id=announcement_id, group_id=group_id)
    await edit_message_safely(callback.message, text=modify_participants_limit_dialogue, reply_markup=keyboard)


@router.message(Announcement.modifying_max_participants, F.text)
async def modify_participants_limit(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    message_id = await state.get_value("message_id")
    await delete_messages_safely(message.chat.id, [message_id, message.message_id])
    back_button_text = await t_for(key="admin_interactions.buttons.back", user_id=message.from_user.id,
                                   default_locale=message.from_user.language_code)
    keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name=back_button_text)
    try:
        participants_limit = int(message.text)
        await message_service.set_participants_limit(group_id=group_id, message_id=announcement_id,
                                                     participants_limit=participants_limit)
        success_message = await t_for(key="admin_interactions.create_announcement.participants_limit_added",
                                      user_id=message.from_user.id,
                                      limit=participants_limit if participants_limit else 0)
        reply = await bot.send_message(chat_id=message.chat.id,
                                       text=success_message,
                                       reply_markup=keyboard)
    except ValueError as e:
        reply = await bot.send_message(chat_id=message.chat.id, text=e.args[0], reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id)


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
    if len(message.text) > 64:
        reply_text = await t_for(key="admin_interactions.create_announcement.payment.title_too_long",
                                 user_id=message.from_user.id)
    else:
        await state.set_state(Announcement.modifying_callback_title)
        reply_text = await t_for(key="admin_interactions.manage_announcement.modify_event_name_dialogue",
                                 user_id=message.from_user.id,
                                 button_name=message.text)

    reply = await bot.send_message(chat_id=message.chat.id, text=reply_text, reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id, button_name=message.text)


@router.message(Announcement.modifying_callback_title, F.text)
async def modify_callback_title(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    message_id = await state.get_value("message_id")
    button_name = await state.get_value("button_name")
    callback_title = message.text if message.text != "skip" else button_name
    await delete_messages_safely(message.chat.id, [message_id, message.message_id])
    back_button_text = await t_for(key="admin_interactions.buttons.back", user_id=message.from_user.id)
    keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name=back_button_text)
    if len(callback_title) > 64:
        reply_text = await t_for(key="admin_interactions.create_announcement.payment.title_too_long",
                                 user_id=message.from_user.id)
    else:
        try:
            await message_service.add_button_to_announcement(group_id=group_id, message_id=announcement_id,
                                                             button_text=button_name,
                                                             event_name=callback_title)
            reply_text = await t_for(key="admin_interactions.manage_announcement.button_and_event_modified",
                                     user_id=message.from_user.id,
                                     button_name=button_name, event_name=callback_title)
        except ValueError as e:
            reply_text = e.args[0]

    reply = await bot.send_message(chat_id=message.chat.id, text=reply_text, reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.modify_invitation_group))
async def show_modify_invite_group_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    group_id = callback_data.group_id
    groups = await admin_service.get_my_groups_for_invitation(callback.from_user.id, group_id)
    keyboard = await build_invitation_group_keyboard(groups=groups, modify=True)
    text = await t_for(key="admin_interactions.create_announcement.payment.invitation_group_dialogue",
                       user_id=callback.from_user.id)

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

    back_button_text = await t_for(key="admin_interactions.buttons.back", user_id=callback.from_user.id)
    keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name=back_button_text)
    success_text = await t_for(key="admin_interactions.manage_announcement.invitation_group_modified",
                               user_id=callback.from_user.id,
                               group_title=reward_group.title)
    return await edit_message_safely(message=callback.message, text=success_text, reply_markup=keyboard)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.remove_payment_product))
@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.remove_early_bird_payment_product))
async def show_remove_payment_product_dialogue(callback: CallbackQuery, callback_data: AdminCallback,
                                               state: FSMContext):
    await state.update_data(announcement_id=callback_data.announcement_id, group_id=callback_data.group_id)
    announcement = await message_service.get_message(group_id=callback_data.group_id,
                                                     message_id=callback_data.announcement_id)
    if callback_data.action == AdminMenuAction.remove_payment_product:
        text = await t_for(key="admin_interactions.manage_announcement.remove_payment.main",
                           user_id=callback.from_user.id,
                           payment_product_id=announcement.stripe_product_id)
        if announcement.early_bird_stripe_product_id:
            text += await t_for(key="admin_interactions.manage_announcement.remove_payment.early_bird",
                                user_id=callback.from_user.id,
                                payment_product_id=announcement.early_bird_stripe_product_id)
        if announcement.payment_expires_at and isinstance(announcement.payment_expires_at, datetime):
            text += await t_for(key="admin_interactions.manage_announcement.remove_payment.expiration",
                                user_id=callback.from_user.id,
                                expiration_date=announcement.payment_expires_at.strftime("%d %B %Y"))
        if announcement.participants_limit:
            text += await t_for(key="admin_interactions.manage_announcement.remove_payment.participants_limit",
                                user_id=callback.from_user.id,
                                limit=announcement.participants_limit)
        keyboard = await build_remove_payment_keyboard(announcement_id=announcement.message_id,
                                                       group_id=callback_data.group_id, early_bird_only=False,
                                                       locale=callback.from_user.language_code)
    else:
        text = await t_for(key="admin_interactions.manage_announcement.remove_early_bird_payment.main",
                           user_id=callback.from_user.id,
                           payment_product_id=announcement.early_bird_stripe_product_id)
        keyboard = await build_remove_payment_keyboard(announcement_id=announcement.message_id,
                                                       group_id=callback_data.group_id, early_bird_only=True,
                                                       locale=callback.from_user.language_code)
    await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.confirm_remove_payment_product))
@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.confirm_remove_early_bird_payment_product))
async def remove_payment_product(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    back_button_text = await t_for(key="admin_interactions.buttons.back", user_id=callback.from_user.id)
    keyboard = await build_skip_button(announcement_id=callback_data.announcement_id, group_id=callback_data.group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name=back_button_text)
    if callback_data.action == AdminMenuAction.confirm_remove_payment_product:
        try:
            await message_service.remove_payment_product(group_id=callback_data.group_id,
                                                         message_id=callback_data.announcement_id)
            await message_service.remove_button_from_announcement(group_id=callback_data.group_id,
                                                                  message_id=callback_data.announcement_id)
            reply_text = await t_for(key="admin_interactions.manage_announcement.remove_payment.success",
                                     user_id=callback.from_user.id)
        except Exception as e:
            reply_text = await t_for(key="admin_interactions.manage_announcement.remove_payment.error",
                                     user_id=callback.from_user.id,
                                     error=str(e))
    else:
        try:
            await message_service.remove_early_bird_payment_product(group_id=callback_data.group_id,
                                                                    message_id=callback_data.announcement_id)
            reply_text = await t_for(key="admin_interactions.manage_announcement.remove_early_bird_payment.success",
                                     user_id=callback.from_user.id)
        except Exception as e:
            reply_text = await t_for(key="admin_interactions.manage_announcement.remove_early_bird_payment.error",
                                     user_id=callback.from_user.id,
                                     error=str(e))

    await edit_message_safely(message=callback.message, text=reply_text, reply_markup=keyboard)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.add_payment_product))
@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.modify_early_bird_payment_product))
async def show_add_payment_product_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    if callback_data.action == AdminMenuAction.add_payment_product:
        await state.set_state(Announcement.adding_payment_product)
    elif callback_data.action == AdminMenuAction.modify_early_bird_payment_product:
        await state.set_state(Announcement.modifying_early_bird_payment_product)
    await state.update_data(message_id=callback.message.message_id, announcement_id=callback_data.announcement_id,
                            group_id=callback_data.group_id)

    dialogue_text = await t_for(key="admin_interactions.manage_announcement.reply_with_stripe_id",
                                user_id=callback.from_user.id)
    back_button_text = await t_for(key="admin_interactions.buttons.back", user_id=callback.from_user.id)
    keyboard = await build_skip_button(announcement_id=callback_data.announcement_id, group_id=callback_data.group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name=back_button_text)
    await edit_message_safely(message=callback.message, text=dialogue_text, reply_markup=keyboard)


# @router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.modify_early_bird_payment_product))
# async def modify_early_bird_payment_product_dialogue(callback: CallbackQuery, callback_data: AdminCallback,
#                                                      state: FSMContext):
#     await state.set_state(Announcement.modifying_early_bird_payment_product)
#     dialogue_text = await t_for(key="admin_interactions.manage_announcement.reply_with_stripe_id",
#                                 user_id=callback.from_user.id)
#     back_button_text = await t_for(key="admin_interactions.buttons.back", user_id=callback.from_user.id)
#     keyboard = await build_skip_button(announcement_id=callback_data.announcement_id, group_id=callback_data.group_id,
#                                        action=AdminMenuAction.manage_announcements,
#                                        button_name=back_button_text)
#     await edit_message_safely(message=callback.message, text=dialogue_text,
#                               reply_markup=keyboard)
#     await state.update_data(message_id=callback.message.message_id, announcement_id=callback_data.announcement_id,
#                             group_id=callback_data.group_id)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.modify_reward_type))
async def show_modify_reward_type_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await state.set_state(Announcement.modifying_reward_type)
    keyboard = await build_reward_type_keyboard(announcement_id=callback_data.announcement_id,
                                                group_id=callback_data.group_id, modify=True)
    text = await t_for(key="admin_interactions.manage_announcement.choose_reward_type",
                       user_id=callback.from_user.id)
    await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)


@router.callback_query(Announcement.modifying_reward_type,
                       AdminCallback.filter(F.action == AdminMenuAction.set_reward_type))
async def modify_reward_type(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await state.update_data(message_id=callback.message.message_id, announcement_id=callback_data.announcement_id,
                            group_id=callback_data.group_id)
    if callback_data.reward_type == "invite":
        text = await t_for(key="admin_interactions.create_announcement.payment.invitation_group_dialogue",
                           user_id=callback.from_user.id)
        text += "\n"
        text += await t_for(key="admin_interactions.manage_announcement.invitation_group_reminder",
                            user_id=callback.from_user.id)
        main_group_id = await state.get_value("group_id")
        groups = await admin_service.get_my_groups_for_invitation(callback.from_user.id, main_group_id)
        keyboard = await build_invitation_group_keyboard(groups, modify=True)
    else:
        announcement = await message_service.get_message(group_id=callback_data.group_id,
                                                         message_id=callback_data.announcement_id)
        reward = await reward_service.update_reward(announcement_id=announcement.id, reward_type="message")
        if not reward.thank_you:
            return await show_modify_thank_you_message_dialogue(callback, callback_data, state)
        text = await t_for(key="admin_interactions.manage_announcement.reward_message_set",
                           user_id=callback.from_user.id)
        back_button_text = await t_for(key="admin_interactions.buttons.back", user_id=callback.from_user.id)
        keyboard = await build_skip_button(announcement_id=callback_data.announcement_id,
                                           group_id=callback_data.group_id,
                                           action=AdminMenuAction.manage_announcements,
                                           button_name=back_button_text)
    return await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.modify_thank_you_message))
async def show_modify_thank_you_message_dialogue(callback: CallbackQuery, callback_data: AdminCallback,
                                                 state: FSMContext):
    await state.set_state(Announcement.modifying_thank_you_message)
    await state.update_data(message_id=callback.message.message_id)
    if callback_data.announcement_id:
        await state.update_data(announcement_id=callback_data.announcement_id)
    text = await t_for(key="admin_interactions.create_announcement.payment.thank_you_message_dialogue",
                       user_id=callback.from_user.id)
    back_button_text = await t_for(key="admin_interactions.buttons.back", user_id=callback.from_user.id)
    keyboard = await build_skip_button(announcement_id=callback_data.announcement_id, group_id=callback_data.group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name=back_button_text)
    await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)


@router.message(Announcement.modifying_thank_you_message, F.text)
async def modify_thank_you_message(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    message_id = await state.get_value("message_id")
    await delete_messages_safely(message.chat.id, [message.message_id, message_id])
    back_button_text = await t_for(key="admin_interactions.buttons.back", user_id=message.from_user.id)
    keyboard = await build_skip_button(announcement_id=announcement_id,
                                       group_id=group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name=back_button_text)
    try:
        announcement = await message_service.get_message(group_id=group_id,
                                                         message_id=announcement_id)
        await reward_service.update_reward(announcement_id=announcement.id, thank_you_message=message.text)

        text = await t_for(key="admin_interactions.create_announcement.payment.thank_you_message_set",
                           user_id=message.from_user.id,
                           thank_you_message=message.text)
    except Exception as e:
        text = await t_for(key="admin_interactions.manage_announcement.thank_you_message_error",
                           user_id=message.from_user.id,
                           error=str(e))

    reply = await bot.send_message(chat_id=message.chat.id, text=text, reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.get_announcement_participants))
async def get_announcement_participants(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    payments = await message_service.get_participants(message_id=callback_data.announcement_id,
                                                      group_id=callback_data.group_id)
    text = await build_participants_list(payments)
    back_button_text = await t_for(key="admin_interactions.buttons.back", user_id=callback.from_user.id,
                                   default_locale=callback.from_user.language_code)
    keyboard = await build_skip_button(announcement_id=callback_data.announcement_id,
                                       group_id=callback_data.group_id,
                                       action=AdminMenuAction.manage_announcements,
                                       button_name=back_button_text)
    await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)
