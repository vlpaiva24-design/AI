# tg-bot-starter

Стартовый Telegram-бот на **aiogram 3**, готовый к деплою на **Render**.
Локально работает через polling, на Render — через webhook. Режим выбирается автоматически.

## Структура

- `bot.py` — точка входа (polling / webhook)
- `handlers.py` — команды и сообщения (тут добавляешь логику)
- `config.py` — настройки из переменных окружения
- `requirements.txt` — зависимости
- `render.yaml` — конфиг для деплоя на Render
- `.env.example` — пример переменных окружения

## Локальный запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# открой .env и впиши BOT_TOKEN от @BotFather
python bot.py
```

Бот стартует в режиме polling. Напиши ему в Telegram `/start`.

## Получить токен

1. Открой [@BotFather](https://t.me/BotFather) в Telegram
2. `/newbot` → задай имя и username
3. Скопируй токен в `.env` (локально) или в Environment на Render

## Деплой на Render

1. Запушь проект в репозиторий на GitHub.
2. На Render: **New + → Web Service** → выбери этот репозиторий.
3. Настройки (если не используешь render.yaml):
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`
4. В разделе **Environment** добавь:
   - `BOT_TOKEN` — токен от BotFather
   - `MODE` — `webhook`
   - `WEBHOOK_SECRET` — любая случайная строка
5. Deploy. После старта Render сам выдаёт `RENDER_EXTERNAL_URL`, бот ставит webhook автоматически.

> Бесплатный Web Service на Render засыпает после 15 минут простоя — первый
> ответ после сна будет с задержкой. Для постоянной работы — платный план.
