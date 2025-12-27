from datetime import datetime

from sqlalchemy import BigInteger, String, TIMESTAMP, func, ForeignKey, and_, or_
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.schemas.literals import UserStatus, UserRole


class GroupMember(Base):
    __tablename__ = "group_members"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", onupdate="CASCADE"), nullable=False)

    group_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("groups.id", onupdate="CASCADE"), nullable=False)

    role: Mapped[UserRole | None] = mapped_column(String(50), nullable=True)

    status: Mapped[UserStatus | None] = mapped_column(String(50), nullable=True)

    greeting_message: Mapped[str | None] = mapped_column(String, nullable=True)

    warning_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    joined_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=True)

    left_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="groups")
    group: Mapped["Group"] = relationship("Group", back_populates="members")

    @hybrid_property
    def is_active_admin(self) -> bool:
        return (self.role == "administrator" or self.role == "creator") and self.status == "active"

    @is_active_admin.expression
    def is_active_admin(self):
        return and_(or_(self.role == "administrator", self.role == "creator"), self.status == "active")

    @hybrid_property
    def has_greeting(self) -> bool:
        return self.greeting_message is not None


    def __repr__(self):
        return f"<GroupMember(id={self.id}, user_id={self.user_id}, group_id={self.group_id}, role={self.role}, status={self.status}, joined_at={self.joined_at}, left_at={self.left_at})>"