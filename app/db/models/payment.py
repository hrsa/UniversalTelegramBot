from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, TIMESTAMP, func, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.schemas.literals import PaymentStatus


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)

    message_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("messages.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)

    stripe_payment_id: Mapped[str] = mapped_column(String, nullable=True)

    stripe_product_id: Mapped[str] = mapped_column(String, nullable=True)

    status: Mapped[PaymentStatus | None] = mapped_column(String, nullable=True)

    url: Mapped[str] = mapped_column(String, nullable=True)

    amount: Mapped[int] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    claimed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    user = relationship("User", back_populates="payments")
    message = relationship("Message", back_populates="payments")

    def __repr__(self):
        return f"<Payment (id={self.id}, user_id={self.user_id}, message_id={self.message_id}, status={self.status}, amount={self.amount}, claimed_at={self.claimed_at})>"