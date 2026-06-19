"""Обработчики сообщений и команд бота."""
from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    name = message.from_user.first_name if message.from_user else "друг"
    await message.answer(
        f"Привет, {name}! 👋\n\n"
        "Я стартовый бот. Команды:\n"
        "/start — это сообщение\n"
        "/help — помощь\n"
        "/ping — проверка связи\n\n"
        "Или просто напиши что-нибудь — я повторю."
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Это шаблон бота на aiogram 3, готовый к деплою на Render.\n"
        "Добавляй новые команды в handlers.py."
    )


@router.message(Command("ping"))
async def cmd_ping(message: Message) -> None:
    await message.answer("pong ✅")


@router.message()
async def echo(message: Message) -> None:
    if message.text:
        await message.answer(f"Ты написал: {message.text}")
    else:
        await message.answer("Я пока понимаю только текст 🙂")
