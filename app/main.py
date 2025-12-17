import sys
from contextlib import asynccontextmanager

from aiogram.types import Update
from fastapi import FastAPI, Request, HTTPException
from loguru import logger

from app.config import settings
from app.bot.core import dp, bot
from app.events.emitter import redis_broker
from app.handlers import all_routers
from app.events.listeners import all_listeners
from app.scheduler.setup import setup_scheduler, scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    dp.include_routers(*all_routers)

    await redis_broker.start()
    setup_scheduler()
    await bot.set_webhook(url=f"https://{settings.DOMAIN}/{settings.WEBHOOK_URL}", secret_token=settings.WEBHOOK_SECRET,
                          allowed_updates=["message", "edited_message", "channel_post", "edited_channel_post", "business_connection",
                                           "business_message", "edited_business_message", "deleted_business_message", "message_reaction",
                                           "message_reaction_count", "inline_query", "chosen_inline_result", "callback_query",
                                           "shipping_query", "pre_checkout_query", "purchased_paid_media", "poll", "poll_answer",
                                           "my_chat_member", "chat_member", "chat_join_request", "chat_boost", "removed_chat_boost"])
    print(
        f"Webhook set to:"
        f"https://{settings.DOMAIN}/{settings.WEBHOOK_URL}"
    )

    yield
    await bot.delete_webhook()
    await redis_broker.stop()
    if scheduler.running:
        scheduler.shutdown()


app = FastAPI(lifespan=lifespan, title="aUniversalTelegramBot")
for listener in all_listeners:
    app.include_router(listener)
logger.add(sys.stdout, format="<green>{time}</green> <level>{message}</level>", level="INFO", colorize=True)
logger.add("logs/bot.log", rotation="3 days", retention="12 days", colorize=True,
           format="<green>{time}</green> <level>{message}</level>")


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.post(f"/{settings.WEBHOOK_URL}")
async def handle_update(request: Request):
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")

    if secret_token != settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized, invalid secret token")

    update_data = await request.json()
    update = Update(**update_data)
    await dp.feed_update(update=update, bot=bot)
    logger.info(update.model_dump_json(indent=4, exclude_none=True))
    return {"status": "OK"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}


@app.get("/health")
async def health_check():
    return {"status": "ok"}
