from typing import Literal

FeatureFlag = Literal[
    "greeting_watch",
    "kick_inactive_members",
    "max_warning_count",
    "report_new_members",
    "report_leaving_members",
]

PermissionFlag = Literal[
    "can_be_edited", "is_anonymous", "can_manage_chat", "can_delete_messages", "can_manage_video_chats",
    "can_restrict_members", "can_promote_members", "can_change_info", "can_invite_users", "can_post_stories",
    "can_edit_stories", "can_delete_stories", "can_post_messages", "can_edit_messages", "can_pin_messages",
    "can_manage_topics", "can_manage_direct_messages", "can_manage_voice_chats"]
