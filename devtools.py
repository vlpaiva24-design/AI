"""Инструменты разработчика для агента: shell, запись и чтение файлов.

Позволяют Анне клонировать репозитории, править код и пушить в GitHub
(деплой на хостинге происходит автоматически по пушу).
Все операции идут в изолированной рабочей папке на сервере.
ВНИМАНИЕ: это мощные инструменты. Доступ к боту должен быть только у владельца.
"""
import os
import subprocess

import config

WORKSPACE = "/tmp/agent_ws"
_git_ready = False


def _ensure_workspace() -> None:
    os.makedirs(WORKSPACE, exist_ok=True)


def _setup_git() -> None:
    """Один раз настраивает git-авторизацию из токена."""
    global _git_ready
    if _git_ready or not config.GITHUB_TOKEN:
        return
    subprocess.run(["git", "config", "--global", "user.name", "Anna Bot"], check=False)
    subprocess.run(
        ["git", "config", "--global", "user.email", "anna-bot@users.noreply.github.com"],
        check=False,
    )
    subprocess.run(
        ["git", "config", "--global", "credential.helper", "store"], check=False
    )
    cred_path = os.path.expanduser("~/.git-credentials")
    with open(cred_path, "w", encoding="utf-8") as f:
        f.write(f"https://x-access-token:{config.GITHUB_TOKEN}@github.com\n")
    os.chmod(cred_path, 0o600)
    _git_ready = True


def _mask(text: str) -> str:
    if config.GITHUB_TOKEN and config.GITHUB_TOKEN in text:
        text = text.replace(config.GITHUB_TOKEN, "***")
    return text


# --- реализация ------------------------------------------------------------
def shell(command: str, timeout: int = 120) -> str:
    _ensure_workspace()
    _setup_git()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"Ошибка: команда выполнялась дольше {timeout} секунд и была прервана."
    out = (proc.stdout or "")[-4000:]
    err = (proc.stderr or "")[-3000:]
    parts = [f"exit code: {proc.returncode}"]
    if out:
        parts.append("stdout:\n" + out)
    if err:
        parts.append("stderr:\n" + err)
    return _mask("\n\n".join(parts))


def write_file(path: str, content: str) -> str:
    _ensure_workspace()
    full = os.path.normpath(os.path.join(WORKSPACE, path))
    if not full.startswith(WORKSPACE):
        return "Ошибка: путь вне рабочей папки."
    os.makedirs(os.path.dirname(full) or WORKSPACE, exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Записан файл {path} ({len(content)} символов)."


def read_file(path: str) -> str:
    full = os.path.normpath(os.path.join(WORKSPACE, path))
    if not full.startswith(WORKSPACE):
        return "Ошибка: путь вне рабочей папки."
    try:
        with open(full, encoding="utf-8") as f:
            return f.read()[:6000]
    except FileNotFoundError:
        return f"Файл не найден: {path}"


# --- схемы для модели ------------------------------------------------------
DEV_TOOLS = [
    {
        "name": "shell",
        "description": (
            "Выполнить shell-команду в рабочей папке на сервере "
            "(git, ls, cat, npm и т.п.). Возвращает код возврата и вывод. "
            "Через неё клонируешь репозитории, коммитишь и пушишь."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Записать (создать или перезаписать) файл в рабочей папке. "
            "Удобнее для больших файлов, чем echo через shell. "
            "path — путь относительно рабочей папки (например repo/index.html)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "read_file",
        "description": "Прочитать файл из рабочей папки по относительному пути.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
]

_DISPATCH = {"shell": shell, "write_file": write_file, "read_file": read_file}


def run_tool(name: str, tool_input: dict) -> str:
    func = _DISPATCH.get(name)
    if func is None:
        return f"Неизвестный инструмент: {name}"
    try:
        return func(**tool_input)
    except Exception as exc:  # noqa: BLE001
        return f"Ошибка инструмента {name}: {exc}"
