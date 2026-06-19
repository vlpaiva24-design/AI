"""Точка входа. Запускает бота в режиме polling (локально) или webhook (Render)."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiohttp import web

import config
from handlers import router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(router)
    return dp


async def run_polling() -> None:
    """Локальный режим: бот сам опрашивает Telegram."""
    bot = Bot(token=config.BOT_TOKEN)
    dp = build_dispatcher()
    # На всякий случай убираем webhook, чтобы polling не конфликтовал.
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
        await bot.set_webhook(
            url=webhook_url,
            secret_token=config.WEBHOOK_SECRET,
            drop_pending_updates=True,
        )
        logger.info("Webhook установлен: %s", webhook_url)

    app = web.Application()
    # Простой health-check, чтобы Render видел, что сервис живой.
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
