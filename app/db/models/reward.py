from datetime import datetime

from sqlalchemy import BigInteger, TIMESTAMP, func, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.schemas.literals import RewardType


class Reward(Base):
    __tablename__ = "rewards"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


    message_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("messages.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)

    type: Mapped[RewardType | None] = mapped_column(String, nullable=True)

    thank_you: Mapped[str] = mapped_column(String, nullable=True)

    group_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("groups.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    message = relationship("Message", back_populates="reward")
    group = relationship("Group", back_populates="rewards")

    def __repr__(self):
        return f"<Reward (id={self.id}, user_id={self.user_id}, message_id={self.message_id}, type={self.type}, thank_you={self.thank_you}, group_id={self.group_id}, created_at={self.created_at})>"