"""Мозги агента: Claude (Anthropic API) с инструментами + память диалога."""
import asyncio
import logging

import anthropic

import config
import tools

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

BASE_SYSTEM_PROMPT = (
    "Ты — личный агент-ассистент Владимира, доступный через Telegram. "
    "Отвечай дружелюбно, по делу и кратко, если не просят развёрнуто. "
    "У тебя есть инструменты: поиск в интернете (web_search), чтение страниц "
    "(fetch_url) и запуск Python-кода (run_python). "
    "Используй их, когда это реально помогает: для свежих фактов — поиск, "
    "для вычислений и обработки данных — код. Не выдумывай факты, которые "
    "можно проверить поиском. Если использовал поиск — указывай ссылки в ответе. "
    "Пиши на языке пользователя."
)

# Цены за миллион токенов (вход, выход) по моделям.
_PRICES = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}

# Память диалога в оперативной памяти: user_id -> список сообщений.
# Внимание: на бесплатном/перезапускаемом Render история обнуляется.
_history: dict[int, list[dict]] = {}

# Счётчик токенов: user_id -> {"input": N, "output": M}.
_usage: dict[int, dict[str, int]] = {}


def _cost(input_tokens: int, output_tokens: int) -> float:
    in_price, out_price = _PRICES.get(config.ANTHROPIC_MODEL, (3.0, 15.0))
    return input_tokens / 1_000_000 * in_price + output_tokens / 1_000_000 * out_price


def _build_system(user_id: int) -> str:
    """Системный промпт со встроенным счётчиком токенов."""
    u = _usage.get(user_id, {"input": 0, "output": 0})
    total = u["input"] + u["output"]
    cost = _cost(u["input"], u["output"])
    return (
        BASE_SYSTEM_PROMPT
        + "\n\nСЧЁТЧИК ТОКЕНОВ (с момента запуска сервиса): "
        + f"вход {u['input']}, выход {u['output']}, всего {total}. "
        + f"Примерная стоимость ${cost:.4f} (модель {config.ANTHROPIC_MODEL}). "
        + "Если пользователь спросит про токены, расход или стоимость — "
        + "назови эти числа. Учти: они не включают текущий запрос."
    )


def usage_text(user_id: int) -> str:
    """Готовая сводка для команды /usage."""
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
            system=_build_system(user_id),
            tools=tools.TOOLS,
            messages=history,
        )
        # Учитываем израсходованные токены.
        u = _usage.setdefault(user_id, {"input": 0, "output": 0})
        u["input"] += response.usage.input_tokens
        u["output"] += response.usage.output_tokens

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
