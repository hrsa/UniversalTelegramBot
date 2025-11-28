from faststream.redis import RedisBroker

from app.config import settings

redis_broker = RedisBroker(f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}")

async def emit_event(event_type: str, event_data):
    channel = f"events.{event_type}"
    print(f"Emitting event to channel {channel}: {event_data}")
    await redis_broker.publish(event_data, f"events.{event_type}")
    print(f"Event emitted to channel {channel}")

