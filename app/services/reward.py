from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped

from app.db.models.reward import Reward
from app.db.repositories import reward as reward_repo
from app.schemas.literals import RewardType
from app.services.message import MessageService


class RewardService:
    def __init__(self, session: async_sessionmaker, message_service: MessageService):
        self.session = session

    async def get_reward(self, reward_id: int | Mapped[int] | None = None,
                         announcement_id: int | Mapped[int] | None = None) -> Reward | None:
        async with self.session() as session:
            reward = await reward_repo.get_reward(session, reward_id=reward_id, message_id=announcement_id)
        return reward

    async def create_reward(self, announcement_id: int| Mapped[int], reward_type: RewardType, thank_you_message: str | None = None,
                            group_id: int | None = None) -> Reward:
        async with self.session() as session:
            reward = await reward_repo.create_reward(session=session, message_id=announcement_id, group_id=group_id,
                                                     reward_type=reward_type, thank_you=thank_you_message)
        return reward

    async def update_reward(self, reward_id: int | Mapped[int] | None = None,
                            announcement_id: int | Mapped[int] | None = None,
                            reward_type: RewardType | None = None, thank_you_message: str | None = None,
                            group_id: int | None = None) -> Reward:
        async with self.session() as session:
            reward = await reward_repo.update_reward(session=session, reward_id=reward_id, message_id=announcement_id,
                                                     reward_type=reward_type, thank_you=thank_you_message,
                                                     group_id=group_id)
        return reward

    async def get_thank_you_message(self, username: str, reward_id: int | Mapped[int] | None = None,
                                    announcement_id: int | Mapped[int] | None = None) -> str | None:
        reward = await self.get_reward(reward_id=reward_id, announcement_id=announcement_id)
        if reward is None:
            return None
        return reward.thank_you.replace("%USERNAME%", f"@{username}") if reward.thank_you else None
