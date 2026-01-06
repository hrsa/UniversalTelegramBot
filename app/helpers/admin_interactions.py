from typing import Sequence, get_args

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, MaybeInaccessibleMessageUnion
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from sqlalchemy.orm import Mapped

from app.bot.core import bot
from app.db.models.group import Group
from app.db.models.message import Message
from app.db.models.payment import Payment
from app.schemas.callbacks import AdminCallback, AdminMenuAction, GroupFeature
from app.schemas.group_features import ChannelFeatures, GroupFeatures
from app.schemas.literals import RewardType
from app.services.group import GroupService
from app.services.message import get_payment_counts
from app.services.translation import t_for


async def edit_message_safely(message: MaybeInaccessibleMessageUnion, text: str,
                              reply_markup: InlineKeyboardMarkup | None = None):
    try:
        return await message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            logger.warning(e)
            pass
        else:
            logger.error(e)
    except Exception as e:
        logger.error(f"Failed to edit message {message.message_id}: {e}")


async def delete_messages_safely(chat_id: int, message_ids: Sequence[int]):
    for message_id in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.error(f"Failed to delete message {message_id} in chat {chat_id}: {e}")


async def build_group_selection_keyboard(groups: Sequence[Group]) -> InlineKeyboardMarkup:
    if len(groups) == 0:
        return InlineKeyboardMarkup(inline_keyboard=[])

    builder = InlineKeyboardBuilder()
    for group in groups:
        builder.button(text=group.title,
                       callback_data=AdminCallback(level=0, action=AdminMenuAction.select_group,
                                                   group_id=group.id).pack())

    builder.adjust(1)
    return builder.as_markup()


async def build_main_features_keyboard(group_id: int, features: GroupFeatures | ChannelFeatures,
                                       is_creator: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Make a new announcement ➡️",
                   callback_data=AdminCallback(level=1, action=AdminMenuAction.make_announcement,
                                               group_id=group_id).pack())
    builder.button(text="Manage announcements ➡️",
                   callback_data=AdminCallback(level=1, action=AdminMenuAction.manage_announcements,
                                               group_id=group_id).pack())

    for name, value in features.model_dump().items():
        button_text = name.replace("_", " ").capitalize()
        if name == "greeting_watch":
            button_text = "Greeting Watch ➡️"
            action = AdminMenuAction.open_feature
        elif name == "allow_payments":
            if is_creator:
                button_text = "Disable payments" if value else "Enable Payments"
                action = AdminMenuAction.toggle_bool
            else:
                continue
        elif isinstance(value, bool):
            button_text += " ✅" if value else " ❌"
            action = AdminMenuAction.toggle_bool
        else:
            button_text += f" ({value})"
            action = AdminMenuAction.set_value

        builder.button(text=button_text,
                       callback_data=AdminCallback(level=1, action=action,
                                                   feature_name=getattr(GroupFeature, name),
                                                   group_id=group_id).pack())

    builder.button(text="⬅️ Back",
                   callback_data=AdminCallback(level=1, action=AdminMenuAction.back).pack())

    builder.adjust(1)
    return builder.as_markup()


async def build_greeting_watch_keyboard(group_id: int, group_service: GroupService) -> InlineKeyboardMarkup:
    features = await group_service.get_features(group_id)
    group = await group_service.get_or_create_group(group_id)

    toggle_text = "Disable greetings" if features.greeting_watch else "Enable greetings"
    greeting_action = "Change greeting message" if group.greeting_message else "Set greeting message"
    reminder_action = "Change reminder message" if group.reminder_message else "Set reminder message"
    builder = InlineKeyboardBuilder()

    if group.greeting_message and group.reminder_message:
        builder.button(text=toggle_text,
                       callback_data=AdminCallback(level=2, action=AdminMenuAction.toggle_bool,
                                                   feature_name=GroupFeature.greeting_watch,
                                                   group_id=group_id).pack())

    builder.button(text=greeting_action,
                   callback_data=AdminCallback(level=2,
                                               action=AdminMenuAction.set_greeting_message,
                                               group_id=group_id).pack())

    builder.button(text=reminder_action,
                   callback_data=AdminCallback(level=2,
                                               action=AdminMenuAction.set_reminder_message,
                                               group_id=group_id).pack())

    builder.button(text="⬅️ Back",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.back,
                                               group_id=group_id).pack())
    builder.adjust(1)
    return builder.as_markup()


async def build_greeting_watch_text(group_id: int, username: str, group_service: GroupService):
    group = await group_service.get_or_create_group(group_id)

    if not group.greeting_message:
        message_text = f"{group.title} has no greeting message yet. Please set it to enable greeting watch!"
    elif not group.reminder_message:
        message_text = f"{group.title} has no reminder message yet. Please set it to enable greeting watch!"
    else:
        message_text = f"{group.title} has the following:\n\n" \
                       "Greeting message:\n" \
                       f"{await group_service.get_greeting_message(group_id=group.id, username=username)} \n\n" \
                       f"Reminder message:\n" \
                       f"{await group_service.get_reminder_message(group_id=group.id, username=username)}"

    return message_text


async def build_confirm_announcement_keyboard(group_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Improve with AI 🤖",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.rewrite_announcement,
                                               group_id=group_id).pack())
    builder.button(text="⬅️ Back",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.back,
                                               group_id=group_id).pack())
    builder.button(text="Confirm ✅",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.confirm_announcement,
                                               group_id=group_id).pack())
    builder.adjust(1,2)
    return builder.as_markup()

async def build_confirm_ai_vs_human_announcement_keyboard(group_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="AI version 🤖",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.confirm_ai_announcement,
                                               group_id=group_id).pack())
    builder.button(text="Human version 🌏",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.confirm_announcement,
                                               group_id=group_id).pack())
    builder.button(text="⬅️ Back",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.back,
                                               group_id=group_id).pack())
    builder.adjust(2,1)
    return builder.as_markup()

async def build_modify_ai_vs_human_announcement_keyboard(group_id: int, announcement_id: int, offset: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="AI version 🤖",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.confirm_ai_announcement,
                                               announcement_offset=offset,
                                               announcement_id=announcement_id,
                                               group_id=group_id).pack())
    builder.button(text="Human version 🌏",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.manage_announcements,
                                               announcement_offset=offset,
                                               announcement_id=announcement_id,
                                               group_id=group_id).pack())
    builder.adjust(1)
    return builder.as_markup()

async def build_confirm_pin_keyboard(group_id: int, announcement_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text="✅",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.confirm_pin,
                                               group_id=group_id,
                                               announcement_id=announcement_id).pack()),
    builder.button(text="❌",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.back,
                                               group_id=group_id).pack())
    builder.adjust(2)
    return builder.as_markup()


async def build_announcement_mgmt_message(announcement: Message | None, group_id: int, count: int,
                                          offset: int, can_add_payments: bool | None = False,
                                          can_pin_announcements: bool | None = False) -> tuple[
    str, InlineKeyboardMarkup]:
    builder = InlineKeyboardBuilder()
    if not announcement:
        text = "No announcements yet."
        builder.button(text="⬅️ Back",
                       callback_data=AdminCallback(level=2, action=AdminMenuAction.back,
                                                   group_id=group_id).pack())
        return text, builder.as_markup()
    text = await build_announcement_data(announcement)
    confirmed, expired, pending, waiting = await get_payment_counts(announcement)
    no_current_payments = confirmed + pending + waiting == 0
    button_count = 0
    if offset > 0:
        button_count += 1
        builder.button(text="⬅️", callback_data=AdminCallback(level=2, action=AdminMenuAction.manage_announcements,
                                                              announcement_offset=offset - 1,
                                                              group_id=group_id).pack())
    if offset + 1 < count:
        button_count += 1
        builder.button(text="➡️", callback_data=AdminCallback(level=2, action=AdminMenuAction.manage_announcements,
                                                              announcement_offset=offset + 1,
                                                              group_id=group_id
                                                              ).pack())
    builder.button(text="Improve with AI 🤖",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.rewrite_announcement,
                                               announcement_offset=offset,
                                               announcement_id=announcement.message_id,
                                               group_id=group_id).pack())

    if can_pin_announcements:
        builder.button(text="Un-pin 📌" if announcement.is_pinned else "Pin 📌",
                       callback_data=AdminCallback(level=2, action=AdminMenuAction.confirm_pin,
                                                   announcement_offset=offset,
                                                   announcement_id=announcement.message_id,
                                                   group_id=group_id
                                                   ).pack())
    if can_add_payments:
        await add_payment_buttons(builder, announcement, group_id)
    if (not announcement.payments or no_current_payments) and announcement.can_be_deleted:
        builder.button(text="Delete 🗑️",
                       callback_data=AdminCallback(level=2, action=AdminMenuAction.delete_announcement,
                                                   announcement_offset=offset,
                                                   announcement_id=announcement.message_id,
                                                   group_id=group_id
                                                   ).pack())

    builder.button(text="⬅️ Back",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.back,
                                               group_id=group_id).pack())
    if button_count > 1:
        builder.adjust(2, 1)
    else:
        builder.adjust(1)
    return text, builder.as_markup()


async def add_payment_buttons(builder: InlineKeyboardBuilder, announcement: Message, group_id: int):
    confirmed, expired, pending, waiting = await get_payment_counts(announcement)
    no_current_payments = confirmed + pending + waiting == 0
    if announcement.payments and len(announcement.payments) > 0:
        builder.button(text="Participants list",
                       callback_data=AdminCallback(level=2, action=AdminMenuAction.get_announcement_participants,
                                                   announcement_id=announcement.message_id, group_id=group_id).pack())
    if announcement.stripe_product_id:
        builder.button(text="Modify expiration date" if announcement.payment_expires_at else "Set expiration date",
                       callback_data=AdminCallback(level=2, action=AdminMenuAction.modify_expiration_date,
                                                   announcement_id=announcement.message_id, group_id=group_id).pack())
        builder.button(text="Modify max participants",
                       callback_data=AdminCallback(level=2, action=AdminMenuAction.modify_max_participants,
                                                   announcement_id=announcement.message_id, group_id=group_id).pack())
        builder.button(text="Modify button name",
                       callback_data=AdminCallback(level=2, action=AdminMenuAction.modify_callback_button_title,
                                                   announcement_id=announcement.message_id, group_id=group_id).pack())
        if (not announcement.payments) or (announcement.payments and no_current_payments):
            builder.button(text="Modify reward type",
                           callback_data=AdminCallback(level=2, action=AdminMenuAction.modify_reward_type,
                                                       announcement_id=announcement.message_id,
                                                       group_id=group_id).pack())
        if announcement.reward and announcement.reward.type == "invite" and no_current_payments:
            builder.button(text="Modify invitation group",
                           callback_data=AdminCallback(level=2, action=AdminMenuAction.modify_invitation_group,
                                                       announcement_id=announcement.message_id,
                                                       group_id=group_id).pack())

        if announcement.reward:
            builder.button(
                text="Modify \"Thank you\" message" if announcement.reward.thank_you else "Add \"Thank you\" message",
                callback_data=AdminCallback(level=2, action=AdminMenuAction.modify_thank_you_message,
                                            announcement_id=announcement.message_id,
                                            group_id=group_id).pack())

    if announcement.stripe_product_id is None:
        builder.button(text="Add payment",
                       callback_data=AdminCallback(level=2, action=AdminMenuAction.add_payment_product,
                                                   announcement_id=announcement.message_id,
                                                   group_id=group_id).pack())
    elif announcement.payments and no_current_payments:
        builder.button(text="Remove payment",
                       callback_data=AdminCallback(level=2, action=AdminMenuAction.remove_payment_product,
                                                   announcement_id=announcement.message_id,
                                                   group_id=group_id).pack())
    if announcement.stripe_product_id and announcement.early_bird_stripe_product_id is None:
        builder.button(text="Add early bird payment",
                       callback_data=AdminCallback(level=2, action=AdminMenuAction.modify_early_bird_payment_product,
                                                   announcement_id=announcement.message_id,
                                                   group_id=group_id).pack())
    if announcement.early_bird_stripe_product_id:
        builder.button(text="Remove early bird payment",
                       callback_data=AdminCallback(level=2, action=AdminMenuAction.remove_early_bird_payment_product,
                                                   announcement_id=announcement.message_id, group_id=group_id).pack())


async def build_announcement_delete_confirmation(announcement: Message, offset: int) -> tuple[
    str, InlineKeyboardMarkup]:
    builder = InlineKeyboardBuilder()
    text = await build_announcement_data(announcement, header="Are you sure you want to delete the announcement?")

    builder.button(text="⬅️ Back",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.back,
                                               announcement_offset=offset,
                                               announcement_id=announcement.message_id,
                                               group_id=announcement.group_id).pack())

    builder.button(text="Delete 🗑️",
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.confirm_delete_announcement,
                                               announcement_offset=offset,
                                               announcement_id=announcement.message_id,
                                               group_id=announcement.group_id
                                               ).pack())
    builder.adjust(2)
    return text, builder.as_markup()


async def build_announcement_data(announcement: Message, header: str | None = None) -> str:
    creation_date = announcement.created_at.strftime("%d.%m.%Y - %H:%M")
    expiration_date = announcement.payment_expires_at.strftime("%d.%m.%Y") if announcement.payment_expires_at else None
    text = f"{header}\n\n" if header else ""
    text += (f"<code>{creation_date}</code>\n\n"
             f"{announcement.text}\n\n")
    text += "<code>"
    if expiration_date:
        text += f"<b>Payment expiration date</b>: {expiration_date if expiration_date else 'N/A'}"
    text += f"\n<b>Max participants</b>: {announcement.participants_limit if announcement.participants_limit else 'Unlimited'}"
    if announcement.stripe_product_id:
        text += f"\n<b>Stripe product ID</b>: {announcement.stripe_product_id}"
    if announcement.early_bird_stripe_product_id:
        text += f"\n<b>Early bird Stripe product ID</b>: {announcement.early_bird_stripe_product_id}"

    if announcement.reward:
        text += f"\n\n<b>Reward</b>: {announcement.reward.type.capitalize()}"
        if announcement.reward.group:
            text += f" to '<b>{announcement.reward.group.title}</b>'"
        text += f"\n<b>'Thank you' message</b>: \"{announcement.reward.thank_you}\""
    if announcement.payments:
        confirmed, expired, pending, waiting = await get_payment_counts(
            announcement)

        text += (f"\n\n<b>Participants</b>:"
                 f"\n - {confirmed} confirmed"
                 f"\n - {pending} pending"
                 f"\n - {waiting} waiting"
                 f"\n - {expired} expired")
    text += "</code>"
    return text


async def build_skip_button(announcement_id: int, group_id: int, action: AdminMenuAction,
                            button_name: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text=button_name if button_name is not None else "Skip",
                   callback_data=AdminCallback(level=2, action=action,
                                               announcement_id=announcement_id,
                                               group_id=group_id).pack())

    return builder.as_markup()


async def build_reward_type_keyboard(announcement_id: int, group_id: int, modify: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for reward_type in get_args(RewardType):
        builder.button(text=reward_type.capitalize(),
                       callback_data=AdminCallback(level=2, action=AdminMenuAction.set_reward_type,
                                                   announcement_id=announcement_id, group_id=group_id,
                                                   reward_type=reward_type).pack())
    if modify:
        builder.button(text="⬅️ Back",
                       callback_data=AdminCallback(level=2, action=AdminMenuAction.manage_announcements,
                                                   announcement_id=announcement_id,
                                                   group_id=group_id).pack())
        builder.adjust(2, 1)

    return builder.as_markup()


async def build_invitation_group_keyboard(groups: Sequence[Group], modify: bool = False) -> InlineKeyboardMarkup:
    if len(groups) == 0:
        return InlineKeyboardMarkup(inline_keyboard=[])

    builder = InlineKeyboardBuilder()
    for group in groups:
        builder.button(text=group.title,
                       callback_data=AdminCallback(level=2,
                                                   action=AdminMenuAction.set_new_invitation_group if modify else AdminMenuAction.set_invitation_group,
                                                   group_id=group.id).pack())

    builder.adjust(1)
    return builder.as_markup()


async def build_remove_payment_keyboard(announcement_id: int | Mapped[int], group_id: int | Mapped[int],
                                        early_bird_only: bool = False,
                                        locale: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if early_bird_only:
        text = await t_for(key="admin_interactions.manage_announcement.remove_early_bird_payment.confirmation_button")
    else:
        text = await t_for(key="admin_interactions.manage_announcement.remove_payment.confirmation_button")
    back_button_text = await t_for(key="admin_interactions.buttons.back")
    builder.button(text=back_button_text,
                   callback_data=AdminCallback(level=2, action=AdminMenuAction.manage_announcements,
                                               announcement_id=announcement_id,
                                               group_id=group_id).pack())
    builder.button(text=text,
                   callback_data=AdminCallback(level=2,
                                               action=AdminMenuAction.confirm_remove_early_bird_payment_product if early_bird_only else AdminMenuAction.confirm_remove_payment_product,
                                               announcement_id=announcement_id, group_id=group_id).pack())
    builder.adjust(1)
    return builder.as_markup()


async def build_participants_list(payments: Sequence[Payment]) -> str:
    if len(payments) == 0:
        return "No participants yet."
    text = ""
    i = 1
    for payment in payments:
        if not payment.user:
            logger.error(f"Payment {payment.id} has no user attached.")
            continue
        name = payment.user.full_name if payment.user.full_name else " "
        username = f"@{payment.user.username}" if payment.user.username else ""
        text += f"{i}) {name} ({username}) - {payment.status} {payment.amount / 100}€\n"
        i += 1

    return text
