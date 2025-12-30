from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.core import bot
from app.config import settings
from app.db.session import async_session_maker
from app.handlers.admin.admin_interactions import process_group_selection
from app.handlers.admin.callbacks import AdminCallback, AdminMenuAction
from app.handlers.admin.states import AdminPanel, Announcement
from app.helpers.admin_interactions import edit_message_safely, build_confirm_announcement_keyboard, \
    build_confirm_pin_keyboard, delete_messages_safely, build_skip_button, build_reward_type_keyboard, \
    build_invitation_group_keyboard, build_main_features_keyboard
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
                                                              text=announcement_text, is_pinned=False)
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
async def set_announcement_button_name_and_show_callback_title_dialogue(message: Message, state: FSMContext):
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
        text = (F"\"Thank you\" message set to:\n\n"
                F"{message.text}\n\n"
                F"Please choose the group where you'd like to invite the participants.")
        await bot.send_message(chat_id=message.chat.id, text=text, reply_markup=keyboard)
    else:
        announcement_id = await state.get_value("announcement_id")
        announcement = await message_service.get_message(group_id=group_id, message_id=announcement_id)
        await reward_service.create_reward(announcement_id=announcement.id, reward_type=reward_type,
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
async def show_pin_dialogue(callback: CallbackQuery, callback_data: AdminCallback, state: FSMContext):
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
