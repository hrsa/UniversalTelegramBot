from sqlalchemy import BigInteger, String, TIMESTAMP, func, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class GroupPermission(Base):
    __tablename__ = "group_permissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    group_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("groups.id"), nullable=False)

    role: Mapped[str] = mapped_column(String(50), nullable=True)

    custom_title: Mapped[str] = mapped_column(String(80), nullable=True)

    can_be_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    is_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    can_manage_chat: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    can_delete_messages: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    can_manage_video_chats: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    can_restrict_members: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    can_promote_members: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    can_change_info: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    can_invite_users: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    can_post_stories: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    can_edit_stories: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    can_delete_stories: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    can_post_messages: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    can_edit_messages: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    can_pin_messages: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    can_manage_topics: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    can_manage_direct_messages: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    can_manage_voice_chats: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    updated_at: Mapped[str] = mapped_column(TIMESTAMP(timezone=True), onupdate=func.now(), nullable=True)

    group = relationship("Group", back_populates="permissions")

    def __repr__(self):
        return f"<GroupPermission(id={self.id}, group_id={self.group_id}, role={self.role}, can_be_edited={self.can_be_edited}, is_anonymous={self.is_anonymous}, can_manage_chat={self.can_manage_chat}, can_delete_messages={self.can_delete_messages}, can_manage_video_chats={self.can_manage_video_chats}, can_restrict_members={self.can_restrict_members}, can_promote_members={self.can_promote_members}, can_change_info={self.can_change_info}, can_invite_users={self.can_invite_users}, can_post_stories={self.can_post_stories}, can_edit_stories={self.can_edit_stories}, can_delete_stories={self.can_delete_stories}, can_post_messages={self.can_post_messages}, can_edit_messages={self.can_edit_messages}, can_manage_direct_messages={self.can_manage_direct_messages}, can_manage_voice_chats={self.can_manage_voice_chats}, updated_at={self.updated_at})>"
