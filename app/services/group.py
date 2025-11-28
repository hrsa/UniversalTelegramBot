from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.group import Group
from app.db.repositories import group as group_repo
from app.schemas.group_features import GroupFeatures


class GroupService:
    def __init__(self, session: async_sessionmaker):
        self.session = session

    async def get_or_create_group(self, group_id: int, type: str | None = None, title: str | None = None,
                                  status: str | None = None) -> Group:
        async with self.session() as session:
            group = await group_repo.get_or_create_group(session, group_id, type, title, status)

        return group

    async def leave_group(self, group_id: int) -> Group:
        async with self.session() as session:
            group = await group_repo.set_group_status(session, group_id, "left")

        return group

    async def update_group_title(self, group_id: int, title: str) -> Group:
        return await self.get_or_create_group(group_id, title=title)

    async def get_features(self, group_id: int) -> GroupFeatures:
        group = await self.get_or_create_group(group_id)
        return GroupFeatures(**group.features)

    async def feature_is_active(self, group_id: int, feature_name: str) -> bool:
        features = await self.get_features(group_id)
        return getattr(features, feature_name)

    async def get_greeting_message(self, group_id: int, username: str) -> str | None:
        group = await self.get_or_create_group(group_id)
        greeting_message = group.greeting_message
        return greeting_message.replace("%USERNAME%", f"@{username}") if greeting_message else None
