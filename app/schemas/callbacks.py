from enum import Enum

from aiogram.filters.callback_data import CallbackData


class AdminMenuAction(str, Enum):
    select_group = 'sg'
    open_feature = 'of'
    toggle_bool = 'tb'
    set_value = 'sv'
    make_announcement = 'ma'
    manage_announcements = 'mga'
    set_topic = 'st'
    set_announcement_group = 'sgg'
    rewrite_announcement = 'ra'
    skip_adding_picture = 'sap'
    send_announcement = 'sa'
    confirm_edit_announcement = 'cea'
    skip_to_pin_announcement = 'stp'
    add_announcement_button = "aad"
    set_announcement_button_name = 'sbn'
    set_announcement_button_link = 'sbl'
    add_announcement_picture = 'aap'
    modify_callback_button_title = 'mcbt'
    modify_button_name = 'mbn'
    confirm_announcement = 'ca'
    confirm_ai_announcement = 'caia'
    confirm_delete_announcement = 'cda'
    delete_announcement = 'da'
    confirm_pin = 'cp'
    set_greeting_message = 'sgm'
    set_reminder_message = 'srm'
    back = 'b'
    quit = 'q'

class GroupFeature(str, Enum):
    greeting_watch = 'gw'
    kick_inactive_members = 'kim'
    max_warning_count = 'mwc'
    report_new_members = 'rnm'
    report_leaving_members = 'rlm'

class AnnouncementAction(str, Enum):
    join = 'j'


class AdminCallback(CallbackData, prefix='ad'):
    """
    CallbackData for the admin panel.

    Levels:
    0: Group selection list
    1: Main features menu for a selected group
    2: Submenu for a specific feature (e.g., greeting_watch)
    """
    level: int
    action: AdminMenuAction
    announcement_id: int | None = None
    announcement_offset: int | None = None
    topic_id: int | None = None
    group_id: int | None = None
    feature_name: GroupFeature| None = None


class AnnouncementCallback(CallbackData, prefix='an'):
    action: AnnouncementAction
    announcement_id: int
    event_name: str | None = None
