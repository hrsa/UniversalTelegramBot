from datetime import timedelta, datetime, timezone
from typing import Sequence

from app.db.models.group_member import GroupMember
from app.db.session import async_session_maker
from app.events.emitter import emit_event
from app.services.group import GroupService
from app.services.group_member import GroupMemberService
from app.services.user import UserService

user_service = UserService(async_session_maker)
group_service = GroupService(async_session_maker)
group_member_service = GroupMemberService(
    async_session_maker,
    group_service,
    user_service
)


async def find_members_without_greetings_to_notify():
    members: Sequence[GroupMember] = await group_member_service.get_members_without_greetings()

    notify_limit = datetime.now(timezone.utc) - timedelta(days=7)
    kick_limit = datetime.now(timezone.utc) - timedelta(days=14)

    for member in members:
        if member.joined_at <= kick_limit:
            await emit_event("member_with_no_greeting.kick", member.user_id)
        elif member.joined_at <= notify_limit:
            await emit_event("member_with_no_greeting.notify", member.user_id)