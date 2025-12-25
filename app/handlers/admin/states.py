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
    creating_announcement_title = State()
    creating_announcement = State()
    confirming_announcement = State()
    adding_payment_product = State()
    adding_early_bird_payment_product = State()
    setting_button_name = State()
    setting_participants_limit = State()
    setting_payment_expiration_date = State()
    setting_reward_type = State()
    setting_thank_you_message = State()
    setting_invitation_group = State()
    confirming_pin = State()
    confirming_delete_announcement = State()