from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router()

@router.message(CommandStart())
async def start_command(message: Message):
    print(message)
    user = message.from_user
    welcome_text = (
        f"Hello, {user.full_name}!\n\n"
        f"Here is what i know about you: {user.url}"
    )
    await message.answer(welcome_text)