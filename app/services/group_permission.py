from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped

from app.db.models.group_permission import GroupPermission
from app.db.repositories import group_permission as gp_repo
from app.schemas.literals import PermissionFlag


class GroupPermissionService:
    def __init__(self, session: async_sessionmaker):
        self.session = session

    async def get_or_create_group_permissions(self, group_id: int, role: str | None = None,
                                              custom_title: str | None = None, can_be_edited: bool | None = None,
                                              is_anonymous: bool | None = None, can_manage_chat: bool | None = None,
                                              can_delete_messages: bool | None = None, can_manage_video_chats: bool | None = None,
                                              can_restrict_members: bool | None = None, can_promote_members: bool | None = None,
                                              can_change_info: bool | None = None, can_invite_users: bool | None = None,
                                              can_post_stories: bool | None = None, can_edit_stories: bool | None = None,
                                              can_delete_stories: bool | None = None, can_post_messages: bool | None = None,
                                              can_edit_messages: bool | None = None, can_pin_messages: bool | None = None,
                                              can_manage_topics: bool | None = None, can_manage_direct_messages: bool | None = None,
                                              can_manage_voice_chats: bool | None = None) -> GroupPermission:
        async with self.session() as session:
            group_permission = await gp_repo.get_or_create_group_permission(session, group_id=group_id, role=role,
                                                                            custom_title=custom_title,
                                                                            can_be_edited=can_be_edited,
                                                                            is_anonymous=is_anonymous,
                                                                            can_manage_chat=can_manage_chat,
                                                                            can_delete_messages=can_delete_messages,
                                                                            can_manage_video_chats=can_manage_video_chats,
                                                                            can_restrict_members=can_restrict_members,
                                                                            can_promote_members=can_promote_members,
                                                                            can_change_info=can_change_info,
                                                                            can_invite_users=can_invite_users,
                                                                            can_post_stories=can_post_stories,
                                                                            can_edit_stories=can_edit_stories,
                                                                            can_delete_stories=can_delete_stories,
                                                                            can_post_messages=can_post_messages,
                                                                            can_edit_messages=can_edit_messages,
                                                                            can_pin_messages=can_pin_messages,
                                                                            can_manage_topics=can_manage_topics,
                                                                            can_manage_direct_messages=can_manage_direct_messages,
                                                                            can_manage_voice_chats=can_manage_voice_chats)

        return group_permission

    async def check_permission(self, group_id: int | Mapped[int], permission: PermissionFlag) -> bool:
        async with self.session() as session:
            return await gp_repo.check_permission(session, group_id, permission)

    async def bot_is_admin(self, group_id: int) -> bool:
        permissions = await self.get_or_create_group_permissions(group_id=group_id)
        return permissions.role == "administrator"
