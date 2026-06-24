"""Мозги агента: Claude с инструментами, долгой памятью и напоминаниями."""
import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import anthropic

import config
import db
import devtools
import tools

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

BASE_SYSTEM_PROMPT = (
    "Тебя зовут Анна. Ты — личная ассистентка Владимира (женского рода: "
    "говори о себе в женском роде, например «я поняла», «я сделала»), "
    "доступная через Telegram. "
    "Отвечай дружелюбно, по делу и кратко, если не просят развёрнуто. "
    "У тебя есть инструменты: поиск в интернете (web_search), чтение страниц "
    "(fetch_url), запуск Python-кода (run_python). "
    "Используй их, когда это реально помогает. Не выдумывай проверяемые факты. "
    "Если использовал поиск — указывай ссылки. Пиши на языке пользователя."
)

MEMORY_PROMPT = (
    " У тебя есть долгая память и напоминания. "
    "Когда узнаёшь о пользователе что-то важное и постоянное (имя, предпочтения, "
    "контекст, проекты) — сохраняй через remember. "
    "Когда просят напомнить — ставь напоминание через set_reminder, "
    "вычисляя момент времени относительно текущего времени из этого промпта."
)

DEV_PROMPT = (
    " Ты умеешь писать и публиковать код. Инструменты: shell, write_file, read_file. "
    "Рабочая папка на сервере, git уже авторизован токеном. "
    "ВАЖНО про shell: каждая команда выполняется заново из корня рабочей папки, "
    "состояние каталога между вызовами НЕ сохраняется. Поэтому объединяй команды "
    "через && в одном вызове, например: "
    "cd anna-web && git add -A && git commit -m 'add landing' && git push. "
    "Файлы создавай через write_file, указывая путь вместе с папкой репозитория, "
    "например anna-web/index.html. "
    "Выполняй задачу ПОЛНОСТЬЮ за один ответ: склонируй репозиторий (если его папки "
    "ещё нет), создай или поправь файлы, затем git add, commit и push, и только "
    "после этого отвечай пользователю. Не пиши «создаю...» и не останавливайся на "
    "полпути. Пустой репозиторий после клона это нормально, просто добавь файлы. "
    "Если папка репозитория уже есть, не клонируй повторно, работай в ней. "
    "Никогда не выводи токены и секреты. "
    "В конце обязательно дай короткий итог: что сделано, прошёл ли git push, и ссылку."
)

# Инструменты памяти/напоминаний (доступны только при подключённой БД).
MEMORY_TOOLS = [
    {
        "name": "remember",
        "description": "Сохранить важный факт о пользователе в долгую память.",
        "input_schema": {
            "type": "object",
            "properties": {"fact": {"type": "string"}},
            "required": ["fact"],
        },
    },
    {
        "name": "forget",
        "description": "Удалить факт из памяти по его id (id виден в системном промпте).",
        "input_schema": {
            "type": "object",
            "properties": {"fact_id": {"type": "integer"}},
            "required": ["fact_id"],
        },
    },
    {
        "name": "set_reminder",
        "description": (
            "Поставить напоминание. due_at — момент в формате ISO 8601 в местном "
            "времени пользователя (часовой пояс в системном промпте), "
            "например 2026-06-20T09:00:00."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Текст напоминания"},
                "due_at": {"type": "string", "description": "ISO 8601"},
            },
            "required": ["text", "due_at"],
        },
    },
    {
        "name": "list_reminders",
        "description": "Показать активные (несработавшие) напоминания пользователя.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cancel_reminder",
        "description": "Отменить напоминание по его id.",
        "input_schema": {
            "type": "object",
            "properties": {"reminder_id": {"type": "integer"}},
            "required": ["reminder_id"],
        },
    },
]

_PRICES = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}

_history: dict[int, list[dict]] = {}
_usage: dict[int, dict[str, int]] = {}

MAX_MESSAGES = 30
MAX_DB_MESSAGES = 30
MAX_TOOL_ROUNDS = 20


def _all_tools() -> list[dict]:
    extra = list(MEMORY_TOOLS) if config.HAS_DB else []
    if config.HAS_GIT:
        extra += devtools.DEV_TOOLS
    return tools.TOOLS + extra


def _cost(input_tokens: int, output_tokens: int) -> float:
    in_price, out_price = _PRICES.get(config.ANTHROPIC_MODEL, (3.0, 15.0))
    return input_tokens / 1_000_000 * in_price + output_tokens / 1_000_000 * out_price


def usage_text(user_id: int) -> str:
    u = _usage.get(user_id, {"input": 0, "output": 0})
    total = u["input"] + u["output"]
    cost = _cost(u["input"], u["output"])
    return (
        "📊 Расход токенов (с момента запуска сервиса):\n"
        f"• вход: {u['input']}\n"
        f"• выход: {u['output']}\n"
        f"• всего: {total}\n"
        f"• примерная стоимость: ${cost:.4f}\n"
        f"• модель: {config.ANTHROPIC_MODEL}"
    )


async def _build_system(user_id: int) -> str:
    parts = [BASE_SYSTEM_PROMPT]

    if config.HAS_DB:
        parts[0] += MEMORY_PROMPT
    if config.HAS_GIT:
        parts[0] += DEV_PROMPT
        now = datetime.now(ZoneInfo(config.TIMEZONE))
        parts.append(
            f"Текущее время: {now:%Y-%m-%d %H:%M} "
            f"({config.TIMEZONE}, {now:%A})."
        )
        try:
            facts = await db.get_facts(user_id)
            if facts:
                lines = "\n".join(f"#{fid}: {content}" for fid, content in facts)
                parts.append("Что ты знаешь о пользователе:\n" + lines)
        except Exception:  # noqa: BLE001
            logger.exception("Не удалось прочитать память")

    u = _usage.get(user_id, {"input": 0, "output": 0})
    total = u["input"] + u["output"]
    parts.append(
        f"СЧЁТЧИК ТОКЕНОВ (с момента запуска): вход {u['input']}, выход "
        f"{u['output']}, всего {total}, ~${_cost(u['input'], u['output']):.4f}. "
        "Если спросят про расход — назови эти числа (без текущего запроса)."
    )
    return "\n\n".join(parts)


async def _set_reminder(user_id: int, chat_id: int, tool_input: dict) -> str:
    tz = ZoneInfo(config.TIMEZONE)
    try:
        dt = datetime.fromisoformat(tool_input["due_at"])
    except (ValueError, KeyError):
        return "Не понял дату/время. Нужен формат ISO 8601, напр. 2026-06-20T09:00:00."
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    due_utc = dt.astimezone(timezone.utc)
    rid = await db.add_reminder(user_id, chat_id, tool_input["text"], due_utc)
    return f"Напоминание #{rid} поставлено на {dt.astimezone(tz):%Y-%m-%d %H:%M}."


async def _dispatch(name: str, tool_input: dict, user_id: int, chat_id: int) -> str:
    # Безсостояночные инструменты — в отдельном потоке.
    if name in ("web_search", "fetch_url", "run_python"):
        return await asyncio.to_thread(tools.run_tool, name, tool_input)

    if name in ("shell", "write_file", "read_file"):
        return await asyncio.to_thread(devtools.run_tool, name, tool_input)

    # Инструменты с БД — асинхронно.
    if name == "remember":
        await db.add_fact(user_id, tool_input["fact"])
        return "Запомнил."
    if name == "forget":
        await db.delete_fact(user_id, int(tool_input["fact_id"]))
        return "Удалил из памяти."
    if name == "set_reminder":
        return await _set_reminder(user_id, chat_id, tool_input)
    if name == "list_reminders":
        rows = await db.get_reminders(user_id)
        if not rows:
            return "Активных напоминаний нет."
        tz = ZoneInfo(config.TIMEZONE)
        return "\n".join(
            f"#{r['id']}: {r['text']} — {r['due_at'].astimezone(tz):%Y-%m-%d %H:%M}"
            for r in rows
        )
    if name == "cancel_reminder":
        await db.cancel_reminder(user_id, int(tool_input["reminder_id"]))
        return "Напоминание отменено."
    return f"Неизвестный инструмент: {name}"


def _trim(history: list[dict]) -> None:
    while len(history) > MAX_MESSAGES:
        history.pop(0)
    while history and not (
        history[0]["role"] == "user" and isinstance(history[0]["content"], str)
    ):
        history.pop(0)


async def ask(user_id: int, chat_id: int, text: str) -> str:
    if config.HAS_DB:
        history = [
            {"role": role, "content": content}
            for role, content in await db.get_recent_messages(user_id, MAX_DB_MESSAGES)
        ]
    else:
        history = _history.setdefault(user_id, [])
        _trim(history)
    history.append({"role": "user", "content": text})

    answer = "(пустой ответ)"
    too_many = True
    for _ in range(MAX_TOOL_ROUNDS):
        response = await client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=2000,
            system=await _build_system(user_id),
            tools=_all_tools(),
            messages=history,
        )
        u = _usage.setdefault(user_id, {"input": 0, "output": 0})
        u["input"] += response.usage.input_tokens
        u["output"] += response.usage.output_tokens

        history.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            answer = "".join(
                b.text for b in response.content if b.type == "text"
            ).strip() or "(пустой ответ)"
            too_many = False
            break

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                logger.info("Инструмент: %s, ввод: %s", block.name, block.input)
                result = await _dispatch(
                    block.name, dict(block.input), user_id, chat_id
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result),
                    }
                )
        history.append({"role": "user", "content": tool_results})

    if too_many:
        answer = "Слишком много шагов с инструментами. Уточни задачу?"

    # сохраняем чистые текстовые реплики в базу (постоянная память)
    if config.HAS_DB:
        try:
            await db.add_message(user_id, "user", text)
            await db.add_message(user_id, "assistant", answer)
        except Exception:  # noqa: BLE001
            logger.exception("Не удалось сохранить историю диалога")

    return answer


async def reset(user_id: int) -> None:
    _history.pop(user_id, None)
    if config.HAS_DB:
        try:
            await db.clear_messages(user_id)
        except Exception:  # noqa: BLE001
            logger.exception("Не удалось очистить историю диалога")
