from typing import Sequence

from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.group import Group
from app.db.repositories import group as group_repo
from app.schemas.group_features import GroupFeatures


class AdminService:
    def __init__(self, session: async_sessionmaker):
        self.session = session

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
            updated_features = current_features.model_copy(update={feature_name: not current_value})
            updated_group = await group_repo.set_group_features(session, group_id, updated_features.model_dump())

        return updated_group

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
            print(f"message is: {message.text}")
            print(f"hashtag is: {hashtag}")
            group = await group_repo.set_group_greeting(session, group_id, hashtag, message.text)
            return group
