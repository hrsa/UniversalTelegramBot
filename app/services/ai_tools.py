from langchain_core.tools import StructuredTool

from app.schemas.literals import UserRole, UserStatus
from app.services.admin import AdminService
from app.services.group import GroupService
from app.services.group_member import GroupMemberService
from app.services.user import UserService


def serialize_user(user) -> dict | None:
    if user is None:
        return None

    return {
        "id": user.id,
        "username": user.username,
        "is_bot": user.is_bot,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.full_name,
        "email": user.email,
        "locale": user.locale,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def serialize_group_member(group_member) -> dict | None:
    if group_member is None:
        return None

    return {
        "id": group_member.id,
        "user_id": group_member.user_id,
        "group_id": group_member.group_id,
        "role": group_member.role,
        "status": group_member.status,
        "greeting_message": group_member.greeting_message,
        "warning_count": group_member.warning_count,
        "joined_at": group_member.joined_at.isoformat() if group_member.joined_at else None,
        "left_at": group_member.left_at.isoformat() if group_member.left_at else None,
        "has_greeting": group_member.has_greeting,
        "is_active_admin": group_member.is_active_admin,
    }


def serialize_group(group) -> dict:
    return {
        "id": group.id,
        "type": group.type,
        "title": group.title,
        "status": group.status,
        "created_at": group.created_at.isoformat() if group.created_at else None,
        "updated_at": group.updated_at.isoformat() if group.updated_at else None,
    }


def build_group_tools(
        current_user_id: int,
        group_service: GroupService,
        group_member_service: GroupMemberService,
        user_service: UserService,
        admin_service: AdminService,
) -> list[StructuredTool]:
    async def search_users(user_id: int | None = None,
                           first_name: str | None = None, last_name: str | None = None,
                           username: str | None = None, email: str | None = None,
                           user_locale: str | None = None,
                           is_bot: bool | None = None) -> dict:
        try:
            found_users = await admin_service.find_users(admin_user_id=current_user_id, user_id=user_id,
                                                         first_name=first_name, last_name=last_name, username=username,
                                                         email=email, is_bot=is_bot, user_locale=user_locale)
            return {
                "found": True,
                "message": "Users found",
                "users": [serialize_user(user) for user in found_users],
            }
        except ValueError as e:
            return {
                "found": False,
                "message": "User(s) not found",
            }

    async def get_available_groups() -> dict:
        available_groups = await admin_service.get_my_groups(current_user_id)

        if available_groups is None:
            return {
                "found": False,
                "message": "No groups found",
            }

        return {
            "found": True,
            "message": "Groups found",
            "groups": [serialize_group(group) for group in available_groups],
        }

    async def get_group_info(group_id: int) -> dict:
        group = await group_service.get_group(group_id)
        group_admins = await user_service.get_group_admins(group_id)

        current_user_is_admin = any(current_user_id == admin.id for admin in group_admins)

        if group is None or not current_user_is_admin:
            return {
                "found": False,
                "message": "Group not found",
            }

        return {
            "found": True,
            "message": "Group found",
            "group": serialize_group(group),
        }

    async def get_group_members(group_id: int, role: UserRole | None, status: UserStatus | None) -> dict:
        group_members = await group_member_service.get_group_members(group_id, role, status)

        if group_members is None:
            return {
                "found": False,
                "message": "No group members found",
            }

        return {
            "found": True,
            "message": "Group members found",
            "group_members": [
                serialize_group_member(group_member)
                for group_member in group_members
            ],
        }

    return [
        StructuredTool.from_function(
            coroutine=get_group_info,
            name="get_group_info",
            description="Get group info by Telegram group ID."
        ),
        StructuredTool.from_function(
            coroutine=search_users,
            name="search_users",
            description="Search users by any available property."
        ),
        StructuredTool.from_function(
            coroutine=get_group_members,
            name="get_group_members",
            description="Get group members by Telegram group ID, with optional filter by role and/or status."
        ),
        StructuredTool.from_function(
            coroutine=get_available_groups,
            name="get_available_groups",
            description="Get Telegram groups managed by the user."
        )
    ]
