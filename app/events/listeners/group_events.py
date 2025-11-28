from faststream.redis.fastapi import RedisRouter

from app.config import settings
from app.events.schemas import GreetingWatchActivatedEvent

broker = RedisRouter(f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}")

@broker.subscriber("events.greeting_watch_activated")
async def on_greeting_watch_activated(event: GreetingWatchActivatedEvent):
    print("We've got ourselves an event!")
    print(event)
