"""Инструменты агента: веб-поиск, чтение страниц, запуск Python-кода.

Каждый инструмент описан схемой для Anthropic (TOOLS) и реализован функцией.
Все функции синхронные и блокирующие — в агенте вызываются через
asyncio.to_thread, чтобы не блокировать event loop бота.
"""
import os
import subprocess
import sys
import tempfile

import httpx

# ---------------------------------------------------------------------------
# Описание инструментов для модели (то, что Claude "видит")
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "web_search",
        "description": (
            "Поиск в интернете по запросу. Возвращает список результатов "
            "(заголовок, ссылка, краткое описание). Используй для свежей "
            "информации, фактов, новостей, цен — всего, что меняется."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Поисковый запрос"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_url",
        "description": (
            "Загружает веб-страницу по URL и возвращает её текст. "
            "Используй после web_search, чтобы прочитать конкретную страницу."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Полный URL (https://...)"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "run_python",
        "description": (
            "Выполняет переданный Python-код и возвращает его вывод (stdout/stderr). "
            "Используй для вычислений, обработки данных, проверки логики. "
            "Печатай результат через print(). Время выполнения ограничено 15 секунд."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python-код для запуска"},
            },
            "required": ["code"],
        },
    },
]


# ---------------------------------------------------------------------------
# Реализация инструментов
# ---------------------------------------------------------------------------
def web_search(query: str, max_results: int = 5) -> str:
    try:
        from ddgs import DDGS
    except ImportError:  # старое имя пакета
        from duckduckgo_search import DDGS  # type: ignore

    try:
        results = []
        with DDGS() as ddg:
            for r in ddg.text(query, max_results=max_results):
                results.append(
                    f"• {r.get('title', '')}\n  {r.get('href', '')}\n  {r.get('body', '')}"
                )
        return "\n\n".join(results) if results else "Ничего не найдено."
    except Exception as exc:  # noqa: BLE001
        return f"Ошибка поиска: {exc}"


def fetch_url(url: str) -> str:
    try:
        resp = httpx.get(
            url,
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; TGAgent/1.0)"},
        )
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        return f"Не удалось загрузить страницу: {exc}"

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
    except Exception:  # noqa: BLE001 — на крайний случай вернём сырой текст
        text = resp.text

    return text[:6000] if text else "Страница пустая."


def run_python(code: str) -> str:
    with tempfile.NamedTemporaryFile(
        "w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        path = f.name
    try:
        proc = subprocess.run(
            [sys.executable, path],
            capture_output=True,
            text=True,
            timeout=15,
        )
        out = (proc.stdout or "")[-4000:]
        err = (proc.stderr or "")[-2000:]
        parts = []
        if out:
            parts.append(f"stdout:\n{out}")
        if err:
            parts.append(f"stderr:\n{err}")
        return "\n\n".join(parts) if parts else "(код выполнен, вывода нет)"
    except subprocess.TimeoutExpired:
        return "Ошибка: превышено время выполнения (15 секунд)."
    except Exception as exc:  # noqa: BLE001
        return f"Ошибка выполнения: {exc}"
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


# Диспетчер: имя инструмента -> функция
_DISPATCH = {
    "web_search": web_search,
    "fetch_url": fetch_url,
    "run_python": run_python,
}


def run_tool(name: str, tool_input: dict) -> str:
    func = _DISPATCH.get(name)
    if func is None:
        return f"Неизвестный инструмент: {name}"
    try:
        return func(**tool_input)
    except Exception as exc:  # noqa: BLE001
        return f"Ошибка инструмента {name}: {exc}"
