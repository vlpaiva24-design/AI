"""Мозги агента: Claude (Anthropic API) с инструментами + память диалога."""
import asyncio
import logging

import anthropic

import config
import tools

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

SYSTEM_PROMPT = (
    "Ты — личный агент-ассистент Владимира, доступный через Telegram. "
    "Отвечай дружелюбно, по делу и кратко, если не просят развёрнуто. "
    "У тебя есть инструменты: поиск в интернете (web_search), чтение страниц "
    "(fetch_url) и запуск Python-кода (run_python). "
    "Используй их, когда это реально помогает: для свежих фактов — поиск, "
    "для вычислений и обработки данных — код. Не выдумывай факты, которые "
    "можно проверить поиском. Если использовал поиск — указывай ссылки в ответе. "
    "Пиши на языке пользователя."
)

# Память диалога в оперативной памяти: user_id -> список сообщений.
# Внимание: на бесплатном/перезапускаемом Render история обнуляется.
_history: dict[int, list[dict]] = {}

MAX_MESSAGES = 30      # сколько элементов истории держать
MAX_TOOL_ROUNDS = 8    # предохранитель от бесконечного цикла инструментов


def _trim(history: list[dict]) -> None:
    """Обрезает историю, не разрывая пары tool_use / tool_result."""
    while len(history) > MAX_MESSAGES:
        history.pop(0)
    # История должна начинаться с обычного текстового сообщения пользователя,
    # иначе API ругнётся на «висящий» tool_result.
    while history and not (
        history[0]["role"] == "user" and isinstance(history[0]["content"], str)
    ):
        history.pop(0)


async def ask(user_id: int, text: str) -> str:
    """Агентский цикл: модель думает, при необходимости зовёт инструменты."""
    history = _history.setdefault(user_id, [])
    history.append({"role": "user", "content": text})
    _trim(history)

    for _ in range(MAX_TOOL_ROUNDS):
        response = await client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            tools=tools.TOOLS,
            messages=history,
        )
        # Сохраняем ответ модели (может содержать запросы на инструменты).
        history.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            answer = "".join(
                b.text for b in response.content if b.type == "text"
            ).strip()
            return answer or "(пустой ответ)"

        # Выполняем все запрошенные инструменты и возвращаем результаты модели.
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                logger.info("Инструмент: %s, ввод: %s", block.name, block.input)
                result = await asyncio.to_thread(
                    tools.run_tool, block.name, dict(block.input)
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result),
                    }
                )
        history.append({"role": "user", "content": tool_results})

    return "Слишком много шагов с инструментами — останавливаюсь. Уточни задачу?"


def reset(user_id: int) -> None:
    """Очищает историю диалога пользователя."""
    _history.pop(user_id, None)
