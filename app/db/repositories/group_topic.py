import locale

from loguru import logger
from sqlalchemy import Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import Mapped

from app.db.models.group_member import GroupMember
from app.db.models.group_topic import GroupTopic
from app.db.models.user import User


async def get_or_create_topic(
        session: AsyncSession,
        topic_internal_id: int | Mapped[int] | None = None,
        group_id: int | Mapped[int] | None = None,
        topic_id: int | Mapped[int] | None = None,
        name: str | None = None,
) -> GroupTopic:
    topic = await get_topic(session, topic_internal_id=topic_internal_id, group_id=group_id, topic_id=topic_id)
    if topic is None:
        topic = await create_topic(session, group_id=group_id, topic_id=topic_id, name=name)
    return topic


async def create_topic(session: AsyncSession, group_id: int, topic_id: int, name: str,
                       is_closed: bool | None = None) -> GroupTopic:
    topic = GroupTopic(topic_id=topic_id, group_id=group_id, name=name,
                       is_closed=is_closed if is_closed is not None else False)
    session.add(topic)
    await session.commit()
    await session.refresh(topic)
    return topic


async def get_topic(session: AsyncSession, topic_internal_id: int | Mapped[int] | None = None,
                    group_id: int | Mapped[int] | None = None,
                    topic_id: int | Mapped[int] | None = None) -> GroupTopic | None:
    stmt = select(GroupTopic)
    if topic_internal_id is not None:
        stmt = stmt.where(GroupTopic.id == topic_internal_id)
    elif group_id is not None and topic_id is not None:
        stmt = stmt.where(GroupTopic.topic_id == topic_id).where(GroupTopic.group_id == group_id)
    else:
        return None
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_topic(session: AsyncSession, name: str | None = None, topic_internal_id: int | Mapped[int] | None = None,
                       group_id: int | Mapped[int] | None = None,
                       topic_id: int | Mapped[int] | None = None,
                       is_closed: bool | None = None
                       ) -> GroupTopic:
    topic = await get_topic(session, topic_internal_id=topic_internal_id, group_id=group_id, topic_id=topic_id)
    if topic is None:
        raise Exception("topic not found")

    logger.warning(f"Updating topic {topic.name} with new name: {name}, is_closed: {is_closed}")
    logger.warning(f"zazaza {topic}")
    topic.name = name if name is not None else topic.name
    topic.is_closed = is_closed if is_closed is not None else topic.is_closed
    await session.commit()
    await session.refresh(topic)
    return topic
