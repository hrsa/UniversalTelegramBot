from datetime import datetime, timezone, timedelta
from typing import Optional, List

from sqlalchemy import BigInteger, TIMESTAMP, func, Boolean, ForeignKey, String, CheckConstraint
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Message(Base):
    __tablename__ = "messages"

    __table_args__ = (
        CheckConstraint(
            "NOT is_published OR message_id IS NOT NULL",
            name="ck_messages_published_requires_message_id"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    group_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("groups.id", onupdate="CASCADE", ondelete="CASCADE"),
                                          nullable=False)

    topic_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("group_topics.topic_id"), nullable=True)

    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    is_published: Mapped[bool] = mapped_column(Boolean, default=False)

    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)

    text: Mapped[str | None] = mapped_column(String, nullable=True)

    picture: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), onupdate=func.now(), nullable=True)

    @hybrid_property
    def can_be_deleted(self) -> bool:
        return self.created_at is not None and self.created_at > datetime.now(timezone.utc) - timedelta(hours=48)

    group: Mapped["Group"] = relationship("Group", back_populates="messages")
    topic: Mapped["GroupTopic"] = relationship("GroupTopic", back_populates="messages")
    buttons: Mapped[List["Button"]] = relationship("Button", back_populates="message")

    def __repr__(self):
        return (
            f"<Message(id={self.id}, group_id={self.group_id}, message_id={self.message_id}, text={self.text}, picture={self.picture}, "
            f"is_pinned={self.is_pinned}, created_at={self.created_at})>")
