from faststream.redis.fastapi import RedisRouter
from loguru import logger

from app.config import settings
from app.db.session import async_session_maker
from app.events.emitter import emit_event
from app.events.schemas import MemberWithNoGreetingEvent
from app.services.group import GroupService
from app.services.group_member import GroupMemberService
from app.services.group_permission import GroupPermissionService
from app.services.user import UserService, kick_user, notify_user

group_service = GroupService(async_session_maker)
user_service = UserService(async_session_maker)
group_permission_service = GroupPermissionService(async_session_maker)
group_member_service = GroupMemberService(async_session_maker, group_service, user_service)

broker = RedisRouter(f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}")


@broker.subscriber("events.member_with_no_greeting.kick")
async def on_kick_member_with_no_greeting(event: MemberWithNoGreetingEvent):
    kick_inactive_members = await group_service.feature_is_active(event.group_id, "kick_inactive_members")
    can_kick_members = await group_permission_service.check_permission(event.group_id, "can_restrict_members")
    if not kick_inactive_members:
        logger.info(
            f"Tried to kick inactive user {event.user_id}, but the feature 'kick_inactive_members' is disabled for group {event.group_id}.")
        await emit_event("member_with_no_greeting.notify", MemberWithNoGreetingEvent(user_id=event.user_id, group_id=event.group_id))
        return

    user = await user_service.get_or_create_user(event.user_id)
    group = await group_service.get_or_create_group(event.group_id)
    member = await group_member_service.get_or_create_member(event.group_id, event.user_id)

    if member.is_active_admin:
        logger.info(f"Tried to kick active admin {event.user_id}, but it's not possible.")
        return

    if not can_kick_members:
        await user_service.notify_admins(
            group_id=event.group_id,
            message=f"I'm supposed to kick @{user.username} from {group.title}, but I don't have permission to do so. Please, update my permissions!"
        )
        await emit_event("member_with_no_greeting.notify", MemberWithNoGreetingEvent(user_id=event.user_id, group_id=event.group_id))
        return

    await kick_user(event.group_id, event.user_id)
    await user_service.notify_admins(f"I've kicked {user.first_name} {user.last_name} (@{user.username}) from {group.title}.", event.group_id)
    await group_member_service.reset_warning_count(group_id=event.group_id, user_id=event.user_id)


@broker.subscriber("events.member_with_no_greeting.notify")
async def on_notify_member_with_no_greeting(event: MemberWithNoGreetingEvent):
    user = await user_service.get_or_create_user(event.user_id)
    greeting_message = await group_service.get_greeting_message(event.group_id, user.username)
    reminder_message = await group_service.get_reminder_message(event.group_id, user.username)

    await notify_user(
        user_id=event.user_id,
        group_id=event.group_id,
        message=f"{reminder_message}\n\n{greeting_message}")

    await group_member_service.increase_warning_count(group_id=event.group_id, user_id=event.user_id)
