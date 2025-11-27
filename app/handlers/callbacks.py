from enum import Enum

from aiogram.filters.callback_data import CallbackData

class AdminMenuAction(str, Enum):
    select_group = 'sg'
    open_feature = 'of'
    toggle_bool = 'tb'
    set_value = 'sv'
    set_greeting_message = 'sgm'
    back = 'b'
    quit = 'q'

class GroupFeature(str, Enum):
    greeting_watch = 'gw'
    kick_inactive_members = 'kim'
    max_warning_count = 'mwc'
    report_new_members = 'rnm'
    report_leaving_members = 'rlm'


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
    group_id: int | None = None
    feature_name: GroupFeature| None = None