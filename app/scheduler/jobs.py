from datetime import timedelta, datetime, timezone
from typing import Sequence

from loguru import logger

from app.db.models.group_member import GroupMember
from app.db.session import async_session_maker
from app.events.emitter import emit_event
from app.events.schemas import MemberWithNoGreetingEvent, GetGroupAdminsEvent
from app.services.group import GroupService
from app.services.group_member import GroupMemberService
from app.services.message import MessageService
from app.services.payment import PaymentService
from app.services.s3_backup import S3BackupService
from app.services.stripe_payment import StripePaymentService
from app.services.user import UserService, notify_user

user_service = UserService(async_session_maker)
group_service = GroupService(async_session_maker)
group_member_service = GroupMemberService(
    async_session_maker,
    group_service,
    user_service
)
message_service = MessageService(async_session_maker)
payment_service = PaymentService(async_session_maker, message_service)
stripe_service = StripePaymentService()
s3_backup_service = S3BackupService()


async def notify_and_kick_members_without_greetings():
    members: Sequence[GroupMember] = await group_member_service.get_members_without_greetings()

    notify_limit = datetime.now(timezone.utc) - timedelta(days=7)
    kick_limit = datetime.now(timezone.utc) - timedelta(days=14)

    for member in members:
        if member.joined_at <= kick_limit or group_member_service.has_too_many_warnings(member.group_id,
                                                                                        member.user_id):
            logger.info(f"Kicking member {member.user_id} from group {member.group_id}")
            await emit_event("member_with_no_greeting.kick", MemberWithNoGreetingEvent(user_id=member.user_id,
                                                                                       group_id=member.group_id))
        elif member.joined_at <= notify_limit:
            logger.info(
                f"Notifying member {member.user_id} from group {member.group_id}. They have {member.warning_count} warnings.")
            await emit_event("member_with_no_greeting.notify", MemberWithNoGreetingEvent(user_id=member.user_id,
                                                                                         group_id=member.group_id))


async def get_group_admins():
    groups = await group_service.get_active_groups()

    for group in groups:
        await emit_event("get_group_admins", GetGroupAdminsEvent(group_id=group.id))


async def check_expired_messages():
    messages = await message_service.get_expired_messages()
    for message in messages:
        await message_service.remove_button_from_announcement(group_id=message.group_id, message_id=message.message_id)


async def invalidate_old_pending_payments():
    pending_payments = await payment_service.get_payments(status="pending")
    for payment in pending_payments:
        if payment.created_at < datetime.now(timezone.utc) - timedelta(minutes=15):
            await stripe_service.disable_payment_link(payment.stripe_payment_id)
            await payment_service.update_payment(user_id=payment.user_id, announcement_id=payment.message_id,
                                                 status="expired")
            await notify_user(user_id=payment.user_id,
                              message="Your payment link has expired and can't be used anymore.\nPlease click on the announcement again if you still want to join.")


async def activate_waiting_payments():
    waiting_payments = await payment_service.get_payments(status="waiting")
    for payment in waiting_payments:
        is_full, pending = await payment_service.verify_event_capacity(payment.message_id)
        if not is_full:
            await payment_service.update_payment(user_id=payment.user_id, announcement_id=payment.message_id,
                                                 status="pending", created_at=datetime.now(timezone.utc))
            message = (f"Congratulations, a place for you is available! Please click on the link to confirm your participation."
                       f"\n\n{payment.url}\n\n"
                       f"Please remember, this link is valid <b><u>only for 15 minutes</u></b>!")
            await notify_user(user_id=payment.user_id,
                              message=message)


async def upload_backups_to_s3():
    logger.info("Uploading backups to S3")

    try:
        stats = await s3_backup_service.process_backups()

        if stats["found"] > 0:
            logger.info(
                f"Backup upload completed. "
                f"Uploaded: {stats['uploaded']}/{stats['found']}, "
                f"Failed: {stats['failed']}"
            )
        else:
            logger.info("No backup files found.")

    except Exception as e:
        logger.error(f"Failed to upload backups: {e}")
