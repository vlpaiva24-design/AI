"""Доступ к PostgreSQL: долгая память (facts) и напоминания (reminders)."""
import asyncpg

import config

_pool: asyncpg.Pool | None = None


async def init() -> None:
    """Создаёт пул соединений и таблицы (если их ещё нет)."""
    global _pool
    dsn = config.DATABASE_URL.replace("postgres://", "postgresql://", 1)
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS facts (
                id         SERIAL PRIMARY KEY,
                user_id    BIGINT NOT NULL,
                content    TEXT   NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now()
            );
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id         SERIAL PRIMARY KEY,
                user_id    BIGINT NOT NULL,
                chat_id    BIGINT NOT NULL,
                text       TEXT   NOT NULL,
                due_at     TIMESTAMPTZ NOT NULL,
                sent       BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT now()
            );
            """
        )


# --- Долгая память ---------------------------------------------------------
async def add_fact(user_id: int, content: str) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO facts (user_id, content) VALUES ($1, $2)", user_id, content
        )


async def get_facts(user_id: int) -> list[tuple[int, str]]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, content FROM facts WHERE user_id = $1 ORDER BY id", user_id
        )
    return [(r["id"], r["content"]) for r in rows]


async def delete_fact(user_id: int, fact_id: int) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM facts WHERE user_id = $1 AND id = $2", user_id, fact_id
        )


# --- Напоминания -----------------------------------------------------------
async def add_reminder(user_id: int, chat_id: int, text: str, due_at) -> int:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO reminders (user_id, chat_id, text, due_at) "
            "VALUES ($1, $2, $3, $4) RETURNING id",
            user_id,
            chat_id,
            text,
            due_at,
        )
    return row["id"]


async def get_reminders(user_id: int):
    async with _pool.acquire() as conn:
        return await conn.fetch(
            "SELECT id, text, due_at FROM reminders "
            "WHERE user_id = $1 AND sent = FALSE ORDER BY due_at",
            user_id,
        )


async def cancel_reminder(user_id: int, reminder_id: int) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM reminders WHERE user_id = $1 AND id = $2 AND sent = FALSE",
            user_id,
            reminder_id,
        )


async def get_due_reminders():
    """Напоминания, которым пора сработать."""
    async with _pool.acquire() as conn:
        return await conn.fetch(
            "SELECT id, chat_id, text FROM reminders "
            "WHERE sent = FALSE AND due_at <= now() ORDER BY due_at LIMIT 20"
        )


async def mark_sent(reminder_id: int) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE reminders SET sent = TRUE WHERE id = $1", reminder_id
        )
