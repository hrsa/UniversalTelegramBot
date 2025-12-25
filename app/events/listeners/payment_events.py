from datetime import datetime, timezone

from faststream.redis.fastapi import RedisRouter

from app.config import settings
from app.db.session import async_session_maker
from app.events.schemas import PaymentReceivedEvent
from app.services.group import GroupService
from app.services.message import MessageService
from app.services.payment import PaymentService
from app.services.reward import RewardService
from app.services.stripe_payment import StripePaymentService
from app.services.user import UserService, notify_user

broker = RedisRouter(f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}")
group_service = GroupService(async_session_maker)
user_service = UserService(async_session_maker)
message_service = MessageService(async_session_maker)
payment_service = PaymentService(async_session_maker, message_service)
reward_service = RewardService(async_session_maker, message_service)
stripe_service = StripePaymentService()

@broker.subscriber("events.payment_received")
async def on_payment_received(event: PaymentReceivedEvent):
    user = await user_service.get_or_create_user(user_id=event.user_id)
    payment = await payment_service.update_payment(stripe_payment_id=event.payment_link_id, status="paid", claimed_at=datetime.now(timezone.utc))
    await stripe_service.disable_payment_link(event.payment_link_id)

    reward = await reward_service.get_reward(announcement_id=payment.message_id)
    message = await reward_service.get_thank_you_message(username=user.username, reward_id=reward.id)
    if reward.type == "invite":
        invite_link = await group_service.get_group_invite_link(group_id=reward.group_id)
        message += f"\n\n{invite_link}"

    await notify_user(user_id=event.user_id, message=message)