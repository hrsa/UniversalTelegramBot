from datetime import datetime

from sqlalchemy import BigInteger, String, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    type: Mapped[str] = mapped_column(String(50), nullable=True)

    title: Mapped[str] = mapped_column(String(120), nullable=True)

    status: Mapped[str] = mapped_column(String(50), nullable=True)

    features: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    greeting_hashtag: Mapped[str] = mapped_column(String(64), nullable=True)

    greeting_message: Mapped[str] = mapped_column(String(360), nullable=True)

    reminder_message: Mapped[str] = mapped_column(String(360), nullable=True)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), onupdate=func.now(), nullable=True)

    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")
    permissions = relationship("GroupPermission", back_populates="group", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="group", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Group(id={self.id}, type={self.type} title={self.title}, created_at={self.created_at})>"