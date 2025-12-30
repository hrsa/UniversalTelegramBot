from enum import Enum

from aiogram.filters.callback_data import CallbackData

from app.schemas.literals import RewardType


class AdminMenuAction(str, Enum):
    select_group = 'sg'
    open_feature = 'of'
    toggle_bool = 'tb'
    set_value = 'sv'
    make_announcement = 'ma'
    manage_announcements = 'mga'
    confirm_edit_announcement = 'cea'
    confirm_add_payment_product = 'cap'
    add_payment_product = 'app'
    remove_payment_product = 'rpp'
    confirm_remove_payment_product = 'crpp'
    add_early_bird_payment_product = 'abpp'
    remove_early_bird_payment_product = 'rbpp'
    modify_early_bird_payment_product = 'mbpp'
    confirm_remove_early_bird_payment_product = 'crbpp'
    modify_thank_you_message = 'mtym'
    skip_to_pin_announcement = 'stp'
    set_payment_expiration_date = 'sep'
    set_participants_limit = 'spl'
    set_announcement_button_name = 'sbn'
    modify_expiration_date = 'med'
    modify_max_participants = 'mmp'
    modify_callback_title = 'mct'
    modify_callback_button_title = 'mcbt'
    modify_button_name = 'mbn'
    modify_reward_type = 'mrt'
    modify_invitation_group = 'mig'
    set_reward_type = 'srt'
    set_invitation_group = 'sgi'
    set_new_invitation_group = 'ngi'
    confirm_announcement = 'ca'
    confirm_delete_announcement = 'cda'
    get_announcement_participants = 'gap'
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
    allow_payments = 'ap'

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
    group_id: int | None = None
    feature_name: GroupFeature| None = None
    reward_type: RewardType | None = None


class AnnouncementCallback(CallbackData, prefix='an'):
    action: AnnouncementAction
    announcement_id: int
    event_name: str | None = None
