from typing import Literal

from faststream.redis import RedisBroker

from app.config import settings

redis_broker = RedisBroker(f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}")

EventType = Literal[
    "member_with_no_greeting.notify",
    "member_with_no_greeting.kick",
    "get_group_admins",
    "payment_received"
]


async def emit_event(event_type: EventType, event_data):
    channel = f"events.{event_type}"
    print(f"Emitting event to channel {channel}: {event_data}")
    await redis_broker.publish(event_data, f"events.{event_type}")
    print(f"Event emitted to channel {channel}")
