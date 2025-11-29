from faststream.redis.fastapi import RedisRouter

from app.config import settings
from app.events.schemas import GreetingWatchActivatedEvent, MemberWithNoGreetingEvent

broker = RedisRouter(f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}")


@broker.subscriber("events.member_with_no_greeting.kick")
async def on_kick_member_with_no_greeting(event: MemberWithNoGreetingEvent):
    print(event)
    print(f"Kicking member... {event.user_id}")


@broker.subscriber("events.member_with_no_greeting.notify")
async def on_notify_member_with_no_greeting(event: MemberWithNoGreetingEvent):
    print(event)
    print(f"Notifying member... {event.user_id}")
