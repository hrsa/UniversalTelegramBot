from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger

from app.bot.core import bot
from app.config import settings
from app.db.session import async_session_maker
from app.handlers.admin.admin_interactions import process_group_selection
from app.schemas.callbacks import AdminCallback, AdminMenuAction
from app.schemas.states import AdminPanel, Announcement
from app.helpers.admin_interactions import edit_message_safely, build_confirm_announcement_keyboard, \
    build_confirm_pin_keyboard, delete_messages_safely, build_skip_button, build_reward_type_keyboard, \
    build_invitation_group_keyboard, build_main_features_keyboard
from app.services.admin import AdminService
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


@router.callback_query(AdminPanel.managing_features,
                       AdminCallback.filter(F.action == AdminMenuAction.make_announcement))
async def set_announcement_text(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    group = await group_service.get_group(callback_data.group_id)
    await state.update_data(group_id=callback_data.group_id, message_id=callback.message.message_id)
    await state.set_state(Announcement.creating_announcement)
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
    confirmation_text = f"{confirm_announcement_text}\n\n<b>{message.text}</b>"
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
        failed_to_send_text = await t_for(key="admin_interactions.create_announcement.failed_to_send_announcement",
                                          user_id=callback.from_user.id)
        await callback.answer(failed_to_send_text)
        return
    saved_announcement = await message_service.create_message(group_id=group_id, message_id=announcement.message_id,
                                                              text=announcement_text, is_pinned=False)
    if can_add_payments:
        await state.set_state(Announcement.adding_payment_product)
        await state.update_data(message_id=callback.message.message_id, announcement_id=saved_announcement.message_id,
                                group_id=group_id)
        text = await t_for(key="admin_interactions.create_announcement.payment.add_payment_dialogue",
                           user_id=callback.from_user.id)
        dont_add_payment_text = await t_for(key="admin_interactions.create_announcement.buttons.dont_add_payment",
                                            user_id=callback.from_user.id)
        keyboard = await build_skip_button(announcement_id=saved_announcement.message_id,
                                           group_id=saved_announcement.group_id, button_name=dont_add_payment_text,
                                           action=AdminMenuAction.skip_to_pin_announcement)
        await edit_message_safely(message=callback.message, text=text, reply_markup=keyboard)
    else:
        success_text = await t_for(key="admin_interactions.create_announcement.announcement_sent",
                                   user_id=callback.from_user.id)
        pin_dialogue_text = await t_for(key="admin_interactions.create_announcement.pin.pin_dialogue",
                                        user_id=callback.from_user.id)
        if can_pin_announcements:
            await state.set_state(Announcement.confirming_pin)
            keyboard = await build_confirm_pin_keyboard(group_id=group_id,
                                                        announcement_id=saved_announcement.message_id)
            await edit_message_safely(message=callback.message,
                                      text=f"P{success_text}\n{pin_dialogue_text}",
                                      reply_markup=keyboard)
        else:
            group = await group_service.get_group(group_id)
            selected_group_dialogue_text = await t_for(key="admin_interactions.group_management.grou_selected",
                                                       user_id=callback.from_user.id,
                                                       title=group.title)
            features = await group_service.get_features(group_id)
            keyboard = await build_main_features_keyboard(group_id, features,
                                                          callback.from_user.id == settings.ADMIN_TELEGRAM_ID)
            text = f"{success_text}\n\n{selected_group_dialogue_text}"

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
        dont_add_early_bird_text = await t_for(key="admin_interactions.create_announcement.buttons.dont_add_early_bird",
                                               user_id=message.from_user.id)
        payment_added_text = await t_for(key="admin_interactions.create_announcement.payment.main_payment_added",
                                         user_id=message.from_user.id,
                                         product=stripe_product.name)
        early_bird_dialogue_text = await t_for(key="admin_interactions.create_announcement.payment.add_early_bird_dialogue",
                                               user_id=message.from_user.id)
        keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                           action=AdminMenuAction.set_payment_expiration_date,
                                           button_name=dont_add_early_bird_text)
        reply = await bot.send_message(chat_id=message.chat.id,
                                       text=f"{payment_added_text}\n\n{early_bird_dialogue_text}",
                                       reply_markup=keyboard)
    except Exception as e:
        dont_add_payment_text = await t_for(key="admin_interactions.create_announcement.buttons.dont_add_payment",
                                            user_id=message.from_user.id)
        error_text = await t_for(key="admin_interactions.create_announcement.payment.main_payment_failed",
                                 user_id=message.from_user.id,
                                 error=str(e))
        keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                           action=AdminMenuAction.skip_to_pin_announcement,
                                           button_name=dont_add_payment_text)
        reply = await bot.send_message(chat_id=message.chat.id,
                                       text=error_text,
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
            dont_add_expiration_text = await t_for(
                key="admin_interactions.create_announcement.buttons.dont_add_expiration",
                user_id=message.from_user.id)
            early_bird_added_text = await t_for(key="admin_interactions.create_announcement.payment.early_bird_added",
                                                user_id=message.from_user.id,
                                                product=stripe_product.name)
            expiration_dialogue_text = await t_for(
                key="admin_interactions.create_announcement.payment.expiration_date_dialogue",
                user_id=message.from_user.id)
            keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                               action=AdminMenuAction.set_participants_limit,
                                               button_name=dont_add_expiration_text)

            await state.set_state(Announcement.setting_payment_expiration_date)
            reply = await bot.send_message(chat_id=message.chat.id,
                                           text=f"{early_bird_added_text}\n\n{expiration_dialogue_text}",
                                           reply_markup=keyboard)
        except Exception as e:
            dont_add_early_bird_text = await t_for(
                key="admin_interactions.create_announcement.buttons.dont_add_early_bird",
                user_id=message.from_user.id)
            error_text = await t_for(key="admin_interactions.create_announcement.payment.early_bird_failed",
                                     user_id=message.from_user.id,
                                     error=str(e))
            keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                               action=AdminMenuAction.set_payment_expiration_date,
                                               button_name=dont_add_early_bird_text)
            reply = await bot.send_message(chat_id=message.chat.id,
                                           text=error_text,
                                           reply_markup=keyboard)
    else:
        back_text = await t_for(key="admin_interactions.buttons.back", user_id=message.from_user.id)
        keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                           action=AdminMenuAction.manage_announcements,
                                           button_name=back_text)
        try:
            stripe_product = await stripe_payment_service.get_product(message.text)
            await message_service.set_early_bird_stripe_product_id(group_id=group_id, message_id=announcement_id,
                                                                   early_bird_stripe_product_id=stripe_product.id)
            success_text = await t_for(key="admin_interactions.create_announcement.payment.early_bird_added",
                                       user_id=message.from_user.id,
                                       product=stripe_product.name)
            reply = await bot.send_message(chat_id=message.chat.id,
                                           text=success_text,
                                           reply_markup=keyboard)
        except Exception as e:
            error_text = await t_for(key="admin_interactions.create_announcement.payment.early_bird_failed",
                                     user_id=message.from_user.id,
                                     error=str(e))
            reply = await bot.send_message(chat_id=message.chat.id,
                                           text=error_text,
                                           reply_markup=keyboard)

    await state.update_data(message_id=reply.message_id)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.set_payment_expiration_date))
async def show_expiration_date_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await  state.set_state(Announcement.setting_payment_expiration_date)
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    text = await t_for(key="admin_interactions.create_announcement.payment.expiration_date_dialogue",
                       user_id=callback.from_user.id)
    dont_add_expiration_text = await t_for(key="admin_interactions.create_announcement.buttons.dont_add_expiration",
                                           user_id=callback.from_user.id)
    keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                       action=AdminMenuAction.set_participants_limit,
                                       button_name=dont_add_expiration_text)
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
        dont_add_participants_limit_text = await t_for(
            key="admin_interactions.create_announcement.buttons.dont_add_participants_limit",
            user_id=message.from_user.id)
        success_text = await t_for(key="admin_interactions.create_announcement.payment.expiration_date_added",
                                   user_id=message.from_user.id)
        participants_limit_dialogue_text = await t_for(
            key="admin_interactions.create_announcement.payment.participants_limit_dialogue",
            user_id=message.from_user.id)
        keyboard = await build_skip_button(group_id=group_id, announcement_id=announcement_id,
                                           action=AdminMenuAction.set_announcement_button_name,
                                           button_name=dont_add_participants_limit_text)
        reply = await bot.send_message(chat_id=message.chat.id,
                                       text=f"{success_text}\n\n{participants_limit_dialogue_text}",
                                       reply_markup=keyboard)
    except ValueError as e:
        dont_add_expiration_text = await t_for(key="admin_interactions.create_announcement.buttons.dont_add_expiration",
                                               user_id=message.from_user.id)
        keyboard = await build_skip_button(group_id=group_id, announcement_id=announcement_id,
                                           action=AdminMenuAction.set_participants_limit,
                                           button_name=dont_add_expiration_text)
        reply = await bot.send_message(chat_id=message.chat.id, text=e.args[0], reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id)


@router.callback_query(AdminCallback.filter(F.action == AdminMenuAction.set_participants_limit))
async def show_participants_limit_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await state.set_state(Announcement.setting_participants_limit)
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    dont_add_participants_limit_text = await t_for(
        key="admin_interactions.create_announcement.buttons.dont_add_participants_limit",
        user_id=callback.from_user.id)
    participants_limit_dialogue_text = await t_for(
        key="admin_interactions.create_announcement.payment.participants_limit_dialogue",
        user_id=callback.from_user.id)
    keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                       action=AdminMenuAction.set_announcement_button_name,
                                       button_name=dont_add_participants_limit_text)
    await edit_message_safely(callback.message, text=participants_limit_dialogue_text, reply_markup=keyboard)


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
        success_text = await t_for(key="admin_interactions.create_announcement.payment.participants_limit_added",
                                   user_id=message.from_user.id,
                                   limit=participants_limit)
        button_name_dialogue_text = await t_for(
            key="admin_interactions.create_announcement.payment.button_name_dialogue",
            user_id=message.from_user.id)
        reply = await bot.send_message(chat_id=message.chat.id,
                                       text=f"{success_text}\n\n{button_name_dialogue_text}", )
    except ValueError as e:
        dont_add_participants_limit_text = await t_for(
            key="admin_interactions.create_announcement.buttons.dont_add_participants_limit",
            user_id=message.from_user.id)
        keyboard = await build_skip_button(announcement_id=announcement_id, group_id=group_id,
                                           action=AdminMenuAction.set_announcement_button_name,
                                           button_name=dont_add_participants_limit_text)
        reply = await bot.send_message(chat_id=message.chat.id, text=e.args[0], reply_markup=keyboard)
    await state.update_data(message_id=reply.message_id)


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


@router.message(Announcement.setting_callback_title, F.text)
async def set_callback_title(message: Message, state: FSMContext):
    group_id = await state.get_value("group_id")
    announcement_id = await state.get_value("announcement_id")
    message_id = await state.get_value("message_id")
    button_name = await state.get_value("button_name")
    await delete_messages_safely(message.chat.id, [message_id, message.message_id])
    if len(message.text) > 64:
        title_is_too_long_text = await t_for(key="admin_interactions.create_announcement.payment.title_too_long",
                                             user_id=message.from_user.id)
        reply = await bot.send_message(chat_id=message.chat.id, text=title_is_too_long_text)
    else:
        try:
            await message_service.add_button_to_announcement(group_id=group_id, message_id=announcement_id,
                                                             button_text=button_name, event_name=message.text, )
            await state.set_state(Announcement.setting_reward_type)
            keyboard = await build_reward_type_keyboard(announcement_id=announcement_id, group_id=group_id)
            reward_dialogue_text = await t_for(key="admin_interactions.create_announcement.payment.reward_dialogue",
                                               user_id=message.from_user.id)
            reply = await bot.send_message(chat_id=message.chat.id, text=reward_dialogue_text,
                                           reply_markup=keyboard)
        except ValueError as e:
            reply = await bot.send_message(chat_id=message.chat.id, text=e.args[0])
    await state.update_data(message_id=reply.message_id)


@router.callback_query(Announcement.setting_reward_type,
                       AdminCallback.filter(F.action == AdminMenuAction.set_reward_type))
async def set_reward_type(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    await state.update_data(reward_type=callback_data.reward_type, message_id=callback.message.message_id)
    await state.set_state(Announcement.setting_thank_you_message)

    success_text = await t_for(key="admin_interactions.create_announcement.payment.reward_type_set",
                               user_id=callback.from_user.id,
                               type=callback_data.reward_type.capitalize())
    text = F"{success_text}\n\n"
    if callback_data.reward_type == "invite":
        invite_disclaimer = await t_for(key="admin_interactions.create_announcement.payment.invite_disclaimer",
                                        user_id=callback.from_user.id)
        text += f"{invite_disclaimer}\n\n"

    thank_you_message_dialogue_text = await t_for(
        key="admin_interactions.create_announcement.payment.thank_you_message_dialogue",
        user_id=callback.from_user.id)
    text += thank_you_message_dialogue_text
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
        success_text = await t_for(key="admin_interactions.create_announcement.payment.thank_you_message_set",
                                   user_id=message.from_user.id,
                                   thank_you_message=message.text)
        invitation_group_dialogue_text = await t_for(
            key="admin_interactions.create_announcement.payment.invitation_group_dialogue",
            user_id=message.from_user.id)
        await bot.send_message(chat_id=message.chat.id, text=f"{success_text}\n\n{invitation_group_dialogue_text}",
                               reply_markup=keyboard)
    else:
        announcement_id = await state.get_value("announcement_id")
        announcement = await message_service.get_message(group_id=group_id, message_id=announcement_id)
        await reward_service.create_reward(announcement_id=announcement.id, reward_type=reward_type,
                                           thank_you_message=message.text)
        can_pin_announcements = await group_permission_service.check_permission(group_id, "can_pin_messages")
        success_text = await t_for(key="admin_interactions.create_announcement.announcement_sent",
                                   user_id=message.from_user.id)
        if can_pin_announcements:
            await state.set_state(Announcement.confirming_pin)
            pin_dialogue_text = await t_for(key="admin_interactions.create_announcement.pin.pin_dialogue",
                                            user_id=message.from_user.id)
            keyboard = await build_confirm_pin_keyboard(group_id=group_id, announcement_id=announcement_id)
            await bot.send_message(chat_id=message.chat.id,
                                   text=f"{success_text}\n\n{pin_dialogue_text}",
                                   reply_markup=keyboard)
        else:
            group = await group_service.get_group(group_id)
            features = await group_service.get_features(group_id)
            keyboard = await build_main_features_keyboard(group_id, features,
                                                          message.from_user.id == settings.ADMIN_TELEGRAM_ID)
            group_features_dialogue = await t_for(key="admin_interactions.group_management.group_selected",
                                                  user_id=message.from_user.id,
                                                  title=group.title)
            await bot.send_message(chat_id=message.chat.id, text=f"{success_text}\n\n{group_features_dialogue}",
                                   reply_markup=keyboard)
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
        success_text = await t_for(key="admin_interactions.create_announcement.payment.invitation_reward_created",
                                   user_id=callback.from_user.id,
                                   group_title=reward_group.title)
        pin_dialogue_text = await t_for(key="admin_interactions.create_announcement.pin.pin_dialogue",
                                        user_id=callback.from_user.id)
        await edit_message_safely(message=callback.message, text=f"{success_text}\n\n{pin_dialogue_text}",
                                  reply_markup=keyboard)
    else:
        group = await group_service.get_group(group_id)
        features = await group_service.get_features(group_id)
        keyboard = await build_main_features_keyboard(group_id, features,
                                                      callback.from_user.id == settings.ADMIN_TELEGRAM_ID)
        success_text = await t_for(key="admin_interactions.create_announcement.announcement_sent",
                                   user_id=callback.from_user.id)
        group_features_dialogue = await t_for(key="admin_interactions.group_management.group_selected",
                                              user_id=callback.from_user.id,
                                              title=group.title)
        await edit_message_safely(message=callback.message, text=f"{success_text}\n\n{group_features_dialogue}",
                                  reply_markup=keyboard)
        await state.set_state(AdminPanel.managing_features)


@router.callback_query(Announcement.adding_payment_product,
                       AdminCallback.filter(F.action == AdminMenuAction.skip_to_pin_announcement))
@router.callback_query(Announcement.setting_participants_limit,
                       AdminCallback.filter(F.action == AdminMenuAction.skip_to_pin_announcement))
async def show_pin_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
    can_pin_announcements = await group_permission_service.check_permission(callback_data.group_id, "can_pin_messages")
    if not can_pin_announcements:
        keyboard = await build_confirm_pin_keyboard(group_id=callback_data.group_id,
                                                    announcement_id=callback_data.announcement_id)
        pin_dialogue_text = await t_for(key="admin_interactions.create_announcement.pin.pin_dialogue",
                                        user_id=callback.from_user.id)
        await edit_message_safely(message=callback.message, text=pin_dialogue_text,
                                  reply_markup=keyboard)
        await state.set_state(Announcement.confirming_pin)
    else:
        group = await group_service.get_or_create_group(callback_data.group_id)
        features = await group_service.get_features(callback_data.group_id)
        keyboard = await build_main_features_keyboard(callback_data.group_id, features,
                                                      callback.from_user.id == settings.ADMIN_TELEGRAM_ID)
        success_text = await t_for(key="admin_interactions.create_announcement.announcement_sent",
                                   user_id=callback.from_user.id)
        group_features_dialogue = await t_for(key="admin_interactions.group_management.group_selected",
                                              user_id=callback.from_user.id,
                                              title=group.title)
        await edit_message_safely(message=callback.message,
                                  text=f"{success_text}\n\n{group_features_dialogue}",
                                  reply_markup=keyboard)
        await state.set_state(AdminPanel.managing_features)


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
