from typing import Sequence

from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.group import Group
from app.db.repositories import group as group_repo
from app.schemas.group_features import GroupFeatures
from app.services.group_permission import GroupPermissionService


class AdminService:
    def __init__(self, session: async_sessionmaker, group_permission_service: GroupPermissionService):
        self.session = session
        self.gp_service = group_permission_service

    async def get_my_groups(self, user_id) -> Sequence[Group]:
        async with self.session() as session:
            groups = await group_repo.get_groups_managed_by_user(session, user_id)

        return groups

    async def set_feature_flag(self, group_id: int, feature_name: str, value_str: str) -> Group:
        if feature_name not in GroupFeatures.model_fields:
            raise ValueError(f"'{feature_name}' is not a valid feature flag.")

        expected_type = GroupFeatures.model_fields[feature_name].annotation

        coerced_value: bool | int | str
        if expected_type is bool:
            coerced_value = value_str.lower() == 'true'
        elif expected_type is int:
            try:
                coerced_value = int(value_str)
            except ValueError:
                raise TypeError(f"Invalid integer value for {feature_name}: {value_str}")
        else:
            coerced_value = value_str

        async with self.session() as session:
            group = await group_repo.get_or_create_group(session, group_id)
            current_features = GroupFeatures(**group.features)
            updated_features = current_features.model_copy(update={feature_name: coerced_value})
            updated_group = await group_repo.set_group_features(session, group_id, updated_features.model_dump())

        return updated_group

    async def toggle_feature(self, group_id: int, feature_name: str) -> Group:
        if feature_name not in GroupFeatures.model_fields:
            raise ValueError(f"'{feature_name}' is not a valid feature flag.")

        if GroupFeatures.model_fields[feature_name].annotation is not bool:
            raise TypeError(f"Feature '{feature_name}' is not a boolean flag.")

        async with self.session() as session:
            group = await group_repo.get_or_create_group(session, group_id)
            current_features = GroupFeatures(**group.features)
            current_value = getattr(current_features, feature_name)
            if feature_name == "greeting_watch" and current_value == False:
                await self.check_greeting_watch_permissions(group_id)
            updated_features = current_features.model_copy(update={feature_name: not current_value})
            updated_group = await group_repo.set_group_features(session, group_id, updated_features.model_dump())

        return updated_group

    async def check_greeting_watch_permissions(self, group_id: int):
        if not await self.gp_service.bot_is_admin(group_id):
            raise PermissionError("greeting_watch", "Please promote me to group administrators first!")
        if (not await self.gp_service.check_permission(group_id, "can_post_messages")
            and not (await self.gp_service.check_permission(group_id, "can_manage_chat"))):
            raise PermissionError("greeting_watch",
                                  "I need the permission to post messages in order to send greetings!")
        if not await self.gp_service.check_permission(group_id, "can_restrict_members"):
            raise PermissionError("greeting_watch",
                                  "I need the permission to restrict members in order to remove them from the group!")

    async def set_group_greeting(self, group_id: int, message: Message) -> Group:

        if not message.text or not message.entities:
            raise ValueError("Message must contain text and a hashtag.")
        else:
            hashtags = [
                e.extract_from(message.text)
                for e in message.entities
                if e.type == "hashtag"
            ]

        if not hashtags:
            raise ValueError("Message must contain a hashtag.")
        else:
            hashtag = hashtags[0]

        hashtag = hashtag.lower().replace(" ", "_")
        if hashtag[0] != "#":
            hashtag = "#" + hashtag

        async with self.session() as session:
            group = await group_repo.set_group_greeting(session, group_id, hashtag, message.text)
            return group

    async def set_group_reminder(self, group_id: int, reminder_message: str) -> Group:
        if not reminder_message:
            raise ValueError("Reminder message cannot be empty.")
        async with self.session() as session:
            group = await group_repo.set_reminder_message(session, group_id, reminder_message)
            return group