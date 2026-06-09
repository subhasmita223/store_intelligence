"""Async database connection pool. T-15."""

import json
import os
from typing import AsyncGenerator

import asyncpg
from fastapi import Request


_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def init_pool() -> None:
    global _pool
    if _pool is not None:
        return
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    _pool = await asyncpg.create_pool(url, min_size=2, max_size=10, init=_init_connection)


async def close_pool() -> None:
    if _pool is not None:
        await _pool.close()


async def get_db(request: Request) -> AsyncGenerator[asyncpg.Connection, None]:
    assert _pool is not None, "DB pool not initialized"
    async with _pool.acquire() as conn:
        yield conn
