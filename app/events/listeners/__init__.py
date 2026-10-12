# from app.events.listeners.group_events import broker as group_events
# from app.events.listeners.group_member_events import broker as group_member_events
from app.events.listeners import group_events, group_member_events

all_listeners = [group_events, group_member_events]