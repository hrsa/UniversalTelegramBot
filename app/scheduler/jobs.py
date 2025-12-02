from datetime import timedelta, datetime, timezone
from typing import Sequence

from app.db.models.group_member import GroupMember
from app.db.session import async_session_maker
from app.events.emitter import emit_event
from app.events.schemas import MemberWithNoGreetingEvent, GetGroupAdminsEvent
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


async def notify_and_kick_members_without_greetings():
    members: Sequence[GroupMember] = await group_member_service.get_members_without_greetings()

    notify_limit = datetime.now(timezone.utc) - timedelta(days=7)
    kick_limit = datetime.now(timezone.utc) - timedelta(days=14)

    for member in members:
        print(member.joined_at, kick_limit, (member.joined_at <= kick_limit), notify_limit, (member.joined_at <= notify_limit))
        if member.joined_at <= kick_limit:
            print(f"Kicking member {member.user_id} from group {member.group_id}")
            await emit_event("member_with_no_greeting.kick", MemberWithNoGreetingEvent(user_id=member.user_id,
                                                                                       group_id=member.group_id))
        elif member.joined_at <= notify_limit:
            print(f"Notifying member {member.user_id} from group {member.group_id}")
            await emit_event("member_with_no_greeting.notify", MemberWithNoGreetingEvent(user_id=member.user_id,
                                                                                       group_id=member.group_id))

async def get_group_admins():
    groups = await group_service.get_active_groups()

    for group in groups:
        await emit_event("get_group_admins", GetGroupAdminsEvent(group_id=group.id))