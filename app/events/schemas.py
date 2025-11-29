from datetime import datetime

from pydantic import BaseModel


class BaseEvent(BaseModel):
    timestamp: datetime = datetime.now()

class GreetingWatchActivatedEvent(BaseEvent):
    group_id: int

class MemberWithNoGreetingEvent(BaseEvent):
    user_id: int
    group_id: int