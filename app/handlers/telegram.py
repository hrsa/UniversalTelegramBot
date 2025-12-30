from aiogram.types import Update
from fastapi import APIRouter, Request, HTTPException
from loguru import logger

from app.bot.core import dp, bot
from app.config import settings

router = APIRouter()

@router.post(f"/{settings.WEBHOOK_URL}")
async def handle_update(request: Request):
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")

    if secret_token != settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized, invalid secret token")

    update_data = await request.json()
    update = Update(**update_data)
    await dp.feed_update(update=update, bot=bot)
    try:
        logger.info(update.model_dump_json(indent=4, exclude_none=True))
    except Exception as e:
        logger.warning(f"Failed to log update: {e}")
        logger.warning(update_data)
    return {"status": "OK"}