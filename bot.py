"""Точка входа. Запускает бота в режиме polling (локально) или webhook (Render)."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiohttp import web

import config
import db
from handlers import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(router)
    return dp


async def reminder_loop(bot: Bot) -> None:
    """Каждые 30 секунд проверяет БД и отправляет сработавшие напоминания."""
    logger.info("Цикл напоминаний запущен")
    while True:
        try:
            for r in await db.get_due_reminders():
                try:
                    await bot.send_message(
                        r["chat_id"], f"⏰ Напоминание: {r['text']}"
                    )
                finally:
                    await db.mark_sent(r["id"])
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка в цикле напоминаний")
        await asyncio.sleep(30)


async def run_polling() -> None:
    """Локальный режим: бот сам опрашивает Telegram."""
    bot = Bot(token=config.BOT_TOKEN)
    dp = build_dispatcher()

    if config.HAS_DB:
        await db.init()
        asyncio.create_task(reminder_loop(bot))
        logger.info("База данных подключена")

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Запуск в режиме POLLING")
    await dp.start_polling(bot)


def run_webhook() -> None:
    """Режим для Render: Telegram шлёт апдейты на наш HTTPS-эндпоинт."""
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

    bot = Bot(token=config.BOT_TOKEN)
    dp = build_dispatcher()
    webhook_url = f"{config.RENDER_EXTERNAL_URL}{config.WEBHOOK_PATH}"

    async def on_startup(app: web.Application) -> None:
        if config.HAS_DB:
            await db.init()
            app["reminder_task"] = asyncio.create_task(reminder_loop(bot))
            logger.info("База данных подключена")
        await bot.set_webhook(
            url=webhook_url,
            secret_token=config.WEBHOOK_SECRET,
            drop_pending_updates=True,
        )
        logger.info("Webhook установлен: %s", webhook_url)

    app = web.Application()
    app.router.add_get("/", lambda _req: web.Response(text="OK"))

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=config.WEBHOOK_SECRET,
    ).register(app, path=config.WEBHOOK_PATH)

    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)

    logger.info("Запуск в режиме WEBHOOK на порту %s", config.PORT)
    web.run_app(app, host="0.0.0.0", port=config.PORT)


def main() -> None:
    config.validate()
    if config.MODE == "webhook":
        run_webhook()
    else:
        asyncio.run(run_polling())


if __name__ == "__main__":
    main()
