from datetime import datetime
from typing import List

from sqlalchemy import BigInteger, String, TIMESTAMP, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class GroupTopic(Base):
    __tablename__ = "group_topics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    group_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("groups.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)

    topic_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)

    name: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), onupdate=func.now(), nullable=True)

    group: Mapped["Group"] = relationship("Group", back_populates="topics")
    messages: Mapped[List["Message"]] = relationship("Message", back_populates="topic")

    def __repr__(self):
        return f"<GroupTopic(id={self.id}, group_id={self.group_id}, topic_id={self.topic_id}, name={self.name}, created_at={self.created_at})>"