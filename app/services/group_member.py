from typing import Sequence

from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.group_member import GroupMember
from app.schemas.literals import UserRole, UserStatus, GroupType
from app.services.group import GroupService
from app.services.user import UserService
from app.db.repositories import group_member as group_member_repo


class GroupMemberService:
    def __init__(self, session: async_sessionmaker, group_service: GroupService, user_service: UserService):
        self.session = session
        self.group_member_repo = group_member_repo
        self.group_service = group_service
        self.user_service = user_service

    async def get_or_create_member(self, group_id: int, user_id: int, group_title: str | None = None,
                                   group_type: GroupType | None = None, first_name: str | None = None,
                                   last_name: str | None = None, username: str | None = None,
                                   role: UserRole | None = None,
                                   status: UserStatus | None = None, is_bot: bool | None = None):
        async with self.session() as session:
            user = await self.user_service.get_or_create_user(user_id=user_id, first_name=first_name,
                                                              last_name=last_name, username=username, is_bot=is_bot)
            group = await self.group_service.get_or_create_group(group_id=group_id, group_type=group_type, title=group_title)

            group_member = await self.group_member_repo.get_or_create_group_member(session, group_id=group.id,
                                                                                   user_id=user.id, role=role,
                                                                                   status=status)

        return group_member

    async def leave_group(self, group_id: int, user_id: int):
        async with self.session() as session:
            await self.get_or_create_member(group_id, user_id)
            group_member = await self.group_member_repo.set_member_status(session, group_id=group_id, user_id=user_id,
                                                                          status="left")
        return group_member

    async def member_has_greeting(self, group_id: int, user_id: int):
        group_member = await self.get_or_create_member(group_id, user_id)
        return group_member.has_greeting

    async def greeting_processed(self, group_id: int, user_id: int, message: Message) -> bool:
        group = await self.group_service.get_or_create_group(group_id=group_id)

        if not message.text or not message.entities:
            hashtags = []
        else:
            hashtags = [
                e.extract_from(message.text)
                for e in message.entities
                if e.type == "hashtag"
            ]

        if group.greeting_hashtag in hashtags:
            async with self.session() as session:
                await self.group_member_repo.set_member_greeting_message(session, group_id=group.id, user_id=user_id,
                                                                         message=message.text)
                return True
        return False

    async def get_members_without_greetings(self, group_id: int | None = None) -> Sequence[GroupMember]:
        async with self.session() as session:
            return await group_member_repo.get_members_without_greetings(session, group_id)

    async def increase_warning_count(self, group_id: int, user_id: int) -> GroupMember:
        async with self.session() as session:
            return await group_member_repo.increase_warning_count(session, group_id, user_id)

    async def reset_warning_count(self, group_id: int, user_id: int) -> GroupMember:
        async with self.session() as session:
            group_member = await group_member_repo.get_or_create_group_member(session, group_id, user_id)
            group_member.warning_count = 0
            await session.commit()
            await session.refresh(group_member)
            return group_member

    async def has_too_many_warnings(self, group_id: int, user_id: int) -> bool:
        async with self.session() as session:
            group_member = await group_member_repo.get_or_create_group_member(session, group_id, user_id)
            group_features = await self.group_service.get_features(group_id)
            return group_member.warning_count >= group_features.max_warning_count
