"""Конфигурация бота. Читает значения из переменных окружения / .env."""
import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# URL, который Render выдаёт сервису автоматически (для webhook).
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")

# Порт веб-сервера. На Render задаётся автоматически.
PORT = int(os.getenv("PORT", "8080"))

# Секрет для проверки, что запрос к webhook пришёл от Telegram.
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me").strip()

# Путь, по которому Telegram будет слать апдейты.
WEBHOOK_PATH = "/webhook"

# Режим: "polling" или "webhook". Если не задан — определяем автоматически:
# есть внешний URL (значит мы на Render) → webhook, иначе → polling.
_mode = os.getenv("MODE", "").strip().lower()
if _mode in ("polling", "webhook"):
    MODE = _mode
else:
    MODE = "webhook" if RENDER_EXTERNAL_URL else "polling"


def validate() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN не задан. Укажи его в .env (локально) "
            "или в Environment на Render."
        )
    if MODE == "webhook" and not RENDER_EXTERNAL_URL:
        raise RuntimeError(
            "MODE=webhook, но RENDER_EXTERNAL_URL пуст. "
            "На Render эта переменная появляется автоматически."
        )
