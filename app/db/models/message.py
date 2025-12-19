from datetime import datetime

from sqlalchemy import BigInteger, TIMESTAMP, func, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    group_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("groups.id"), nullable=False)

    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)

    is_watched: Mapped[bool] = mapped_column(Boolean, default=False)

    text: Mapped[str] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), onupdate=func.now(), nullable=True)

    group = relationship("Group", back_populates="messages")

    def __repr__(self):
        return f"<Message(id={self.id}, group_id={self.group_id}, message_id={self.message_id}, is_pinned={self.is_pinned}, created_at={self.created_at})>"