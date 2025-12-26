from typing import Sequence

from aiogram.types import ChatInviteLink
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped

from app.bot.core import bot
from app.db.models.group import Group
from app.db.models.message import Message
from app.db.repositories import group as group_repo
from app.db.repositories import message as message_repo
from app.schemas.group_features import GroupFeatures, ChannelFeatures
from app.schemas.literals import FeatureFlag, GroupType, GroupStatus


class GroupService:
    def __init__(self, session: async_sessionmaker):
        self.session = session

    async def get_or_create_group(self, group_id: int | Mapped[int], group_type: GroupType | None = None,
                                  title: str | None = None,
                                  status: GroupStatus | None = None) -> Group:
        async with self.session() as session:
            group = await group_repo.get_or_create_group(session, group_id, group_type, title, status)

        return group

    async def get_active_groups(self) -> Sequence[Group]:
        async with self.session() as session:
            return await group_repo.get_active_groups(session)

    async def get_group(self, group_id: int) -> Group | None:
        async with self.session() as session:
            return await group_repo.get_group(session, group_id)

    async def delete_group(self, group_id: int):
        async with self.session() as session:
            await group_repo.delete_group(session, group_id)

    async def create_group(self, group_id: int, group_type: GroupType | None = None,
                           title: str | None = None,
                           status: GroupStatus | None = None) -> Group:
        async with self.session() as session:
            group = await group_repo.create_group(session, group_id, group_type, title, status)
        return group

    async def update_group(self, group_id: int, new_group_id: int | None = None, title: str | None = None,
                           group_type: GroupType | None = None, status: GroupStatus | None = None,
                           greeting_hashtag: str | None = None,
                           greeting_message: str | None = None, reminder_message: str | None = None):
        async with self.session() as session:
            group = await group_repo.update_group(session=session, group_id=group_id, new_group_id=new_group_id,
                                                  title=title, group_type=group_type, status=status,
                                                  greeting_hashtag=greeting_hashtag,
                                                  greeting_message=greeting_message, reminder_message=reminder_message
                                                  )
        return group

    async def leave_group(self, group_id: int) -> Group:
        return await self.update_group(group_id, status="left")

    async def update_group_title(self, group_id: int, title: str) -> Group:
        return await self.update_group(group_id, title=title)

    async def get_features(self, group_id: int) -> GroupFeatures | ChannelFeatures:
        group = await self.get_or_create_group(group_id)
        if group.type in ("supergroup", "group"):
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

    async def get_group_announcements(self, group_id: int,
                                      offset: int | None = None, limit: int | None = None,
                                      with_rewards: bool = False, with_reward_groups: bool = False,
                                      with_payments: bool = False) -> tuple[Sequence[Message], int]:
        async with self.session() as session:
            return await message_repo.get_messages_for_group(session=session, group_id=group_id, offset=offset,
                                                             limit=limit, with_rewards=with_rewards,
                                                             with_reward_groups=with_reward_groups,
                                                             with_payments=with_payments)

    async def get_group_invite_link(self, group_id: int | Mapped[int], link_name: str | None = None) -> ChatInviteLink:
        group = await self.get_or_create_group(group_id)
        link = await bot.create_chat_invite_link(chat_id=group.id,
                                                 member_limit=1,
                                                 name=link_name if link_name else f"Join {group.title}"
                                                 )

        return link.invite_link
