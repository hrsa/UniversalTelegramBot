from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import Mapped

from app.db.models.group import Group
from app.db.models.reward import Reward
from app.schemas.literals import RewardType


async def get_reward(session: AsyncSession, reward_id: int | None = None,
                     message_id: int | None = None) -> Reward | None:
    if message_id:
        stmt = select(Reward).where(Reward.message_id == message_id)
    elif reward_id:
        stmt = select(Reward).where(Reward.id == reward_id)
    else:
        return None

    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_reward(
        session: AsyncSession,
        message_id: int,
        reward_type: RewardType | None = None,
        thank_you: str | None = None,
        group_id: int | None = None,
) -> Reward:
    reward = await get_reward(session, message_id=message_id)
    if reward is not None:
        raise ValueError(f"Reward for message {message_id} already exists")

    reward = Reward(
        message_id=message_id,
        type=reward_type,
        thank_you=thank_you,
        group_id=group_id,
    )
    session.add(reward)
    await session.commit()

    await session.refresh(reward)
    return reward


async def update_reward(session: AsyncSession,
                        reward_id: int | None = None,
                        message_id: int | None = None,
                        reward_type: RewardType | None = None,
                        thank_you: str | None = None,
                        group_id: int | None = None) -> Reward:
    reward = await get_reward(session, reward_id=reward_id, message_id=message_id)
    if reward is None:
        reward = await create_reward(session, message_id=message_id, reward_type=reward_type, thank_you=thank_you,
                            group_id=group_id)

    if group_id is not None:
        group = await session.execute(select(Group).where(Group.id == group_id))
        group = group.scalar_one_or_none()
        if group is None:
            raise ValueError(f"Group {group_id} not found")

    reward.type = reward_type if reward_type is not None else reward.type
    reward.thank_you = thank_you if thank_you is not None else reward.thank_you
    reward.group_id = group_id if group_id is not None else reward.group_id

    if reward.type == "message":
        reward.group_id = None

    await session.commit()
    await session.refresh(reward)
    return reward


async def delete_reward(session: AsyncSession, reward_id: int | Mapped[int] | None = None,
                        message_id: int | Mapped[int] | None = None):
    reward = await get_reward(session, reward_id=reward_id, message_id=message_id)
    if reward is not None:
        await session.delete(reward)
        await session.commit()
