from datetime import datetime, timezone

from sqlalchemy import BigInteger, TIMESTAMP, func, Boolean, ForeignKey, String
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    group_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("groups.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)

    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)

    is_watched: Mapped[bool] = mapped_column(Boolean, default=False)

    text: Mapped[str] = mapped_column(String, nullable=True)

    stripe_product_id: Mapped[str] = mapped_column(String, nullable=True)

    early_bird_stripe_product_id: Mapped[str] = mapped_column(String, nullable=True)

    participants_limit: Mapped[int] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), onupdate=func.now(), nullable=True)

    payment_expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    @hybrid_property
    def is_expired(self) -> bool:
        return self.payment_expires_at is not None and self.payment_expires_at < datetime.now(timezone.utc)

    group = relationship("Group", back_populates="messages")
    payments = relationship("Payment", back_populates="message")
    reward = relationship("Reward", back_populates="message")

    def __repr__(self):
        return f"<Message(id={self.id}, group_id={self.group_id}, message_id={self.message_id}, is_pinned={self.is_pinned}, stripe_product_id={self.stripe_product_id}, created_at={self.created_at})>"