from sqlalchemy import Sequence, Boolean
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.models.group_member import GroupMember
from app.db.models.group_permission import GroupPermission
from app.db.models.user import User


async def get_or_create_group_permission(
        session: AsyncSession,
        group_id: int,
        role: str | None = None,
        custom_title: str | None = None,
        can_be_edited: bool | None = None,
        is_anonymous: bool | None = None,
        can_manage_chat: bool | None = None,
        can_delete_messages: bool | None = None,
        can_manage_video_chats: bool | None = None,
        can_restrict_members: bool | None = None,
        can_promote_members: bool | None = None,
        can_change_info: bool | None = None,
        can_invite_users: bool | None = None,
        can_post_stories: bool | None = None,
        can_edit_stories: bool | None = None,
        can_delete_stories: bool | None = None,
        can_post_messages: bool | None = None,
        can_edit_messages: bool | None = None,
        can_pin_messages: bool | None = None,
        can_manage_topics: bool | None = None,
        can_manage_direct_messages: bool | None = None,
        can_manage_voice_chats: bool | None = None,
) -> GroupPermission:
    result = await session.execute(
        select(GroupPermission).where(GroupPermission.group_id == group_id)
    )
    group_permission = result.scalar_one_or_none()

    if group_permission is None:
        group_permission = GroupPermission(
            group_id=group_id,
            role=role if role is not None else "member",
            custom_title=custom_title,
            can_be_edited=can_be_edited if can_be_edited is not None else False,
            is_anonymous=is_anonymous if is_anonymous is not None else False,
            can_manage_chat=can_manage_chat if can_manage_chat is not None else False,
            can_delete_messages=can_delete_messages if can_delete_messages is not None else False,
            can_manage_video_chats=can_manage_video_chats if can_manage_video_chats is not None else False,
            can_restrict_members=can_restrict_members if can_restrict_members is not None else False,
            can_promote_members=can_promote_members if can_promote_members is not None else False,
            can_change_info=can_change_info if can_change_info is not None else False,
            can_invite_users=can_invite_users if can_invite_users is not None else False,
            can_post_stories=can_post_stories if can_post_stories is not None else False,
            can_edit_stories=can_edit_stories if can_edit_stories is not None else False,
            can_delete_stories=can_delete_stories if can_delete_stories is not None else False,
            can_post_messages=can_post_messages if can_post_messages is not None else False,
            can_edit_messages=can_edit_messages if can_edit_messages is not None else False,
            can_pin_messages=can_pin_messages if can_pin_messages is not None else False,
            can_manage_topics=can_manage_topics if can_manage_topics is not None else False,
            can_manage_direct_messages=can_manage_direct_messages if can_manage_direct_messages is not None else False,
            can_manage_voice_chats=can_manage_voice_chats if can_manage_voice_chats is not None else False,
        )
        session.add(group_permission)
        await session.commit()
    else:
        update_needed = False

        if role is not None and role != group_permission.role:
            group_permission.role = role
            update_needed = True
        if custom_title is not None and custom_title != group_permission.custom_title:
            group_permission.custom_title = custom_title
            update_needed = True
        if can_be_edited is not None and can_be_edited != group_permission.can_be_edited:
            group_permission.can_be_edited = can_be_edited
            update_needed = True
        if is_anonymous is not None and is_anonymous != group_permission.is_anonymous:
            group_permission.is_anonymous = is_anonymous
            update_needed = True
        if can_manage_chat is not None and can_manage_chat != group_permission.can_manage_chat:
            group_permission.can_manage_chat = can_manage_chat
            update_needed = True
        if can_delete_messages is not None and can_delete_messages != group_permission.can_delete_messages:
            group_permission.can_delete_messages = can_delete_messages
            update_needed = True
        if can_manage_video_chats is not None and can_manage_video_chats != group_permission.can_manage_video_chats:
            group_permission.can_manage_video_chats = can_manage_video_chats
            update_needed = True
        if can_restrict_members is not None and can_restrict_members != group_permission.can_restrict_members:
            group_permission.can_restrict_members = can_restrict_members
            update_needed = True
        if can_promote_members is not None and can_promote_members != group_permission.can_promote_members:
            group_permission.can_promote_members = can_promote_members
            update_needed = True
        if can_change_info is not None and can_change_info != group_permission.can_change_info:
            group_permission.can_change_info = can_change_info
            update_needed = True
        if can_invite_users is not None and can_invite_users != group_permission.can_invite_users:
            group_permission.can_invite_users = can_invite_users
            update_needed = True
        if can_post_stories is not None and can_post_stories != group_permission.can_post_stories:
            group_permission.can_post_stories = can_post_stories
            update_needed = True
        if can_edit_stories is not None and can_edit_stories != group_permission.can_edit_stories:
            group_permission.can_edit_stories = can_edit_stories
            update_needed = True
        if can_delete_stories is not None and can_delete_stories != group_permission.can_delete_stories:
            group_permission.can_delete_stories = can_delete_stories
            update_needed = True
        if can_post_messages is not None and can_post_messages != group_permission.can_post_messages:
            group_permission.can_post_messages = can_post_messages
            update_needed = True
        if can_edit_messages is not None and can_edit_messages != group_permission.can_edit_messages:
            group_permission.can_edit_messages = can_edit_messages
            update_needed = True
        if can_pin_messages is not None and can_pin_messages != group_permission.can_pin_messages:
            group_permission.can_pin_messages = can_pin_messages
            update_needed = True
        if can_manage_topics is not None and can_manage_topics != group_permission.can_manage_topics:
            group_permission.can_manage_topics = can_manage_topics
            update_needed = True
        if can_manage_direct_messages is not None and can_manage_direct_messages != group_permission.can_manage_direct_messages:
            group_permission.can_manage_direct_messages = can_manage_direct_messages
            update_needed = True
        if can_manage_voice_chats is not None and can_manage_voice_chats != group_permission.can_manage_voice_chats:
            group_permission.can_manage_voice_chats = can_manage_voice_chats
            update_needed = True

        if update_needed:
            await session.commit()

    await session.refresh(group_permission)
    return group_permission

async def check_permission(session: AsyncSession, group_id: int, permission: str) -> bool:
    group_permission = await get_or_create_group_permission(session, group_id)

    return getattr(group_permission, permission, False)