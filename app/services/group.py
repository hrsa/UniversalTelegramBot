from typing import Sequence

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.group import Group
from app.db.models.message import Message
from app.db.repositories import group as group_repo
from app.db.repositories import message as message_repo
from app.schemas.group_features import GroupFeatures, ChannelFeatures
from app.schemas.literals import FeatureFlag


class GroupService:
    def __init__(self, session: async_sessionmaker):
        self.session = session

    async def get_or_create_group(self, group_id: int, type: str | None = None, title: str | None = None,
                                  status: str | None = None) -> Group:
        async with self.session() as session:
            group = await group_repo.get_or_create_group(session, group_id, type, title, status)

        return group

    async def get_active_groups(self) -> Sequence[Group]:
        async with self.session() as session:
            return await group_repo.get_active_groups(session)

    async def leave_group(self, group_id: int) -> Group:
        async with self.session() as session:
            group = await group_repo.set_group_status(session, group_id, "left")

        return group

    async def update_group_title(self, group_id: int, title: str) -> Group:
        return await self.get_or_create_group(group_id, title=title)

    async def get_features(self, group_id: int) -> GroupFeatures | ChannelFeatures:
        group = await self.get_or_create_group(group_id)
        if group.type == "supergroup":
            return GroupFeatures(**group.features)
        else:
            return ChannelFeatures(**group.features)

    async def feature_is_active(self, group_id: int, feature_name: FeatureFlag) -> bool:
        features = await self.get_features(group_id)
        return getattr(features, feature_name)

    async def get_greeting_message(self, group_id: int, username: str) -> str | None:
        group = await self.get_or_create_group(group_id)
        greeting_message = group.greeting_message
        return greeting_message.replace("%USERNAME%", f"@{username}") if greeting_message else None

    async def get_reminder_message(self, group_id: int, username: str) -> str | None:
        group = await self.get_or_create_group(group_id)
        reminder_message = group.reminder_message
        return reminder_message.replace("%USERNAME%", f"@{username}") if reminder_message else None

    async def get_group_announcements(self, group_id: int, offset: int | None = None, limit: int | None = None) -> \
    tuple[Sequence[Message], int]:
        async with self.session() as session:
            return await message_repo.get_messages_for_group(session=session, group_id=group_id, offset=offset,
                                                             limit=limit)
