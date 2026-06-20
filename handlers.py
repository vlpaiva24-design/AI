"""Обработчики сообщений и команд бота-ассистента."""
import logging

from aiogram import Router
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

import assistant
import config

logger = logging.getLogger(__name__)
router = Router()

# Telegram режет сообщения длиннее 4096 символов — разбиваем на части.
TG_LIMIT = 4000


def _is_allowed(user_id: int) -> bool:
    # Если разрешённый ID не задан — режим настройки (пускаем никого, но
    # подсказываем ID). Если задан — пускаем только его.
    return config.ALLOWED_USER_ID is not None and user_id == config.ALLOWED_USER_ID


async def _reply_long(message: Message, text: str) -> None:
    for i in range(0, len(text), TG_LIMIT):
        await message.answer(text[i : i + TG_LIMIT])


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if not _is_allowed(user_id):
        await message.answer(
            "👋 Это персональный ассистент.\n\n"
            f"Твой Telegram ID: `{user_id}`\n\n"
            "Чтобы получить доступ, впиши этот ID в переменную "
            "`ALLOWED_USER_ID` на Render.",
            parse_mode="Markdown",
        )
        return
    await message.answer(
        "Привет, Владимир! 👋 Я твой агент на базе Claude.\n\n"
        "Умею искать в интернете, выполнять Python-код, запоминать важное "
        "и ставить напоминания — просто опиши задачу.\n"
        "/reset — забыть контекст\n"
        "/help — подробнее"
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Я личный агент на Claude. Помимо обычного диалога умею:\n"
        "🔎 искать в интернете и читать страницы\n"
        "🐍 выполнять Python-код (расчёты, обработка данных)\n"
        "🧠 запоминать факты о тебе надолго\n"
        "⏰ ставить напоминания и писать тебе вовремя\n\n"
        "/usage — расход токенов и примерная стоимость\n"
        "/reset — очистить контекст текущего диалога."
    )


@router.message(Command("ping"))
async def cmd_ping(message: Message) -> None:
    await message.answer("pong ✅")


@router.message(Command("usage"))
async def cmd_usage(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if not _is_allowed(user_id):
        return
    await message.answer(assistant.usage_text(user_id))


@router.message(Command("reset"))
async def cmd_reset(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    if not _is_allowed(user_id):
        return
    assistant.reset(user_id)
    await message.answer("Память диалога очищена 🧹")


@router.message()
async def chat(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0

    if not _is_allowed(user_id):
        await message.answer(
            "⛔ Нет доступа.\n\n"
            f"Твой Telegram ID: `{user_id}`\n"
            "Если это твой бот — впиши ID в `ALLOWED_USER_ID` на Render.",
            parse_mode="Markdown",
        )
        return

    if not message.text:
        await message.answer("Пока понимаю только текст 🙂")
        return

    # Показываем «печатает…», пока ждём ответ модели.
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)

    try:
        answer = await assistant.ask(user_id, message.chat.id, message.text)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ошибка при обращении к Claude")
        await message.answer(f"⚠️ Ошибка при обращении к модели: {exc}")
        return

    await _reply_long(message, answer)
