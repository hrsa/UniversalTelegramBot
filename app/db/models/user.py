from datetime import datetime
from typing import List, Optional

from sqlalchemy import BigInteger, String, TIMESTAMP, func, Boolean
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    username: Mapped[str] = mapped_column(String(50), nullable=True)

    is_bot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    first_name: Mapped[str] = mapped_column(String(50), nullable=True)

    last_name: Mapped[str] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    groups: Mapped[Optional[List["Group"]]] = relationship("GroupMember", back_populates="user", cascade="all, delete-orphan")
    payments: Mapped[Optional[List["Payment"]]] = relationship("Payment", back_populates="user", cascade="all, delete-orphan")

    @hybrid_property
    def full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name or self.last_name or ""

    def __repr__(self):
        return f"<User(user_id={self.id}, username={self.username}, full_name={self.full_name}, created_at={self.created_at})>"