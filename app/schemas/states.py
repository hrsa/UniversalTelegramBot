from aiogram.fsm.state import StatesGroup, State


class AdminPanel(StatesGroup):
    choosing_group = State()
    managing_features = State()


class GreetingWatch(StatesGroup):
    managing_greeting_watch = State()
    setting_greeting_message = State()
    setting_reminder_message = State()


class Announcement(StatesGroup):
    managing_announcements = State()
    creating_announcement = State()
    adding_announcement_picture = State()
    confirming_announcement = State()
    sending_announcement = State()
    setting_button_name = State()
    setting_button_link = State()
    setting_announcement_group_topic = State()
    modifying_button_name = State()
    modifying_button_link = State()
    confirming_pin = State()
    confirming_delete_announcement = State()