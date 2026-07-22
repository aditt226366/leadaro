"""
Database access. Raw asyncpg, no ORM — the schema already exists as SQL in
migrations/, and an ORM would be a second, drifting definition of it.
"""
import json
import os
from contextlib import asynccontextmanager

import asyncpg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://leadaro:leadaro@localhost:5433/leadaro"
)

_pool: asyncpg.Pool | None = None


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=16,
            # jsonb in / out as dicts rather than strings, everywhere.
            init=_register_codecs,
        )
    return _pool


async def _register_codecs(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    await conn.set_type_codec(
        "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("db pool not initialised")
    return _pool


async def fetch(q: str, *args) -> list[dict]:
    async with pool().acquire() as c:
        return [dict(r) for r in await c.fetch(q, *args)]


async def fetchrow(q: str, *args) -> dict | None:
    async with pool().acquire() as c:
        r = await c.fetchrow(q, *args)
        return dict(r) if r else None


async def fetchval(q: str, *args):
    async with pool().acquire() as c:
        return await c.fetchval(q, *args)


async def execute(q: str, *args) -> str:
    async with pool().acquire() as c:
        return await c.execute(q, *args)


@asynccontextmanager
async def tx():
    """Transaction scope. Use for multi-statement writes."""
    async with pool().acquire() as c:
        async with c.transaction():
            yield c
