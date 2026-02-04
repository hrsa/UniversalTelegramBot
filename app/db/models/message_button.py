from datetime import datetime

from sqlalchemy import BigInteger, TIMESTAMP, func, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Button(Base):
    __tablename__ = "message_buttons"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    message_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("messages.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False)

    text: Mapped[str] = mapped_column(String, nullable=False)

    link: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), onupdate=func.now(), nullable=True)

    message: Mapped["Message"] = relationship("Message", back_populates="buttons")

    def __repr__(self):
        return f"<Button(id={self.id}, message_id={self.message_id}, text={self.text}, link={self.link}, created_at={self.created_at})>"
