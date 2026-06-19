"""Мозги ассистента: вызов Claude (Anthropic API) + память диалога."""
import anthropic

import config

client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

SYSTEM_PROMPT = (
    "Ты — личный ассистент Владимира, доступный через Telegram. "
    "Отвечай дружелюбно, по делу и кратко, если не просят развёрнуто. "
    "Помогай с любыми вопросами: идеи, тексты, код, планирование, разбор задач. "
    "Если чего-то не знаешь наверняка — честно скажи об этом. "
    "Пиши на том языке, на котором обращается пользователь."
)

# Память диалога в оперативной памяти: user_id -> список сообщений.
# Внимание: на бесплатном Render при перезапуске/засыпании история обнуляется.
_history: dict[int, list[dict]] = {}

# Сколько последних реплик (пар вопрос-ответ) держать в контексте.
MAX_MESSAGES = 40  # ~20 обменов


async def ask(user_id: int, text: str) -> str:
    """Отправляет сообщение в Claude с учётом истории диалога."""
    history = _history.setdefault(user_id, [])
    history.append({"role": "user", "content": text})
    # Обрезаем историю, чтобы не раздувать контекст и расходы.
    if len(history) > MAX_MESSAGES:
        del history[: len(history) - MAX_MESSAGES]

    response = await client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=history,
    )
    answer = "".join(
        block.text for block in response.content if block.type == "text"
    ).strip() or "(пустой ответ)"

    history.append({"role": "assistant", "content": answer})
    return answer


def reset(user_id: int) -> None:
    """Очищает историю диалога пользователя."""
    _history.pop(user_id, None)
