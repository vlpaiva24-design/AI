"""Конфигурация бота. Читает значения из переменных окружения / .env."""
import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Ключ Anthropic (мозги ассистента). Берётся на console.anthropic.com.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

# Модель Claude. По умолчанию Sonnet — баланс качества и цены.
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6").strip()

# Telegram ID единственного разрешённого пользователя.
# Если пусто — бот в режиме настройки: подскажет каждому его ID.
_allowed = os.getenv("ALLOWED_USER_ID", "").strip()
ALLOWED_USER_ID = int(_allowed) if _allowed.isdigit() else None

# URL, который Render выдаёт сервису автоматически (для webhook).
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")

# Порт веб-сервера. На Render задаётся автоматически.
PORT = int(os.getenv("PORT", "8080"))

# Секрет для проверки, что запрос к webhook пришёл от Telegram.
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me").strip()

# Путь, по которому Telegram будет слать апдейты.
WEBHOOK_PATH = "/webhook"

# Режим: "polling" или "webhook". Если не задан — определяем автоматически.
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
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY не задан. Получи ключ на console.anthropic.com "
            "и добавь в Environment на Render."
        )
    if MODE == "webhook" and not RENDER_EXTERNAL_URL:
        raise RuntimeError(
            "MODE=webhook, но RENDER_EXTERNAL_URL пуст. "
            "На Render эта переменная появляется автоматически."
        )
