from faststream.redis.fastapi import RedisRouter
from loguru import logger

from app.bot.core import bot
from app.config import settings
from app.db.session import async_session_maker
from app.events.schemas import GetGroupAdminsEvent
from app.services.group import GroupService
from app.services.group_member import GroupMemberService
from app.services.group_permission import GroupPermissionService
from app.services.user import UserService

broker = RedisRouter(f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}")
group_service = GroupService(async_session_maker)
user_service = UserService(async_session_maker)
group_permission_service = GroupPermissionService(async_session_maker)
group_member_service = GroupMemberService(async_session_maker, group_service, user_service)

@broker.subscriber("events.get_group_admins")
async def on_get_group_admins(event: GetGroupAdminsEvent):
    admins = await bot.get_chat_administrators(event.group_id)
    for admin in admins:
        if not admin.user.id == bot.id:
            await group_member_service.get_or_create_member(group_id=event.group_id, user_id=admin.user.id,
                                                        first_name=admin.user.first_name,
                                                        last_name=admin.user.last_name, username=admin.user.username,
                                                        is_bot=admin.user.is_bot, status="active", role=admin.status)
