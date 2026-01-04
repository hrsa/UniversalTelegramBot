import sys
from contextlib import asynccontextmanager

import i18n
from fastapi import FastAPI
from loguru import logger

from app.bot.core import dp, bot
from app.config import settings
from app.events.emitter import redis_broker
from app.events.listeners import all_listeners
from app.handlers import all_routers, api_routers
from app.scheduler.setup import setup_scheduler, scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    i18n.set("filename_format", "{locale}.yml")
    i18n.set("load_path", ["app/translations"])
    i18n.set("fallback", "en")

    dp.include_routers(*all_routers)

    await redis_broker.start()
    setup_scheduler()
    await bot.set_webhook(url=f"https://{settings.DOMAIN}/{settings.WEBHOOK_URL}", secret_token=settings.WEBHOOK_SECRET,
                          allowed_updates=["message", "edited_message", "channel_post", "edited_channel_post",
                                           "business_connection",
                                           "business_message", "edited_business_message", "deleted_business_message",
                                           "message_reaction",
                                           "message_reaction_count", "inline_query", "chosen_inline_result",
                                           "callback_query",
                                           "shipping_query", "pre_checkout_query", "purchased_paid_media", "poll",
                                           "poll_answer",
                                           "my_chat_member", "chat_member", "chat_join_request", "chat_boost",
                                           "removed_chat_boost"])
    logger.info(
        f"Webhook set to:"
        f"https://{settings.DOMAIN}/{settings.WEBHOOK_URL}"
    )

    yield
    await bot.delete_webhook()
    await redis_broker.stop()
    if scheduler.running:
        scheduler.shutdown()


app = FastAPI(lifespan=lifespan, title="aUniversalTelegramBot")
for router in api_routers:
    app.include_router(router)
for listener in all_listeners:
    app.include_router(listener)

logger.add(sys.stdout, format="<green>{time}</green> <level>{message}</level>", level="INFO", colorize=True)
if settings.ENV == "production":
    logger.add("logs/bot.log", rotation="3 days", retention="12 days", colorize=True,
               format="<green>{time}</green> <level>{message}</level>")


@app.get("/health")
async def health_check():
    return {"status": "ok"}

