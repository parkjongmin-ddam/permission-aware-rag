"""Database connection pool management."""

from contextlib import asynccontextmanager
from typing import AsyncIterable

from pgvector.psycopg import register_vector_async
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from permission_aware_rag.config import settings

_pool: AsyncConnectionPool | None = None


async def _configure_connection(conn: AsyncConnection) -> None:
    """Configure each new connection acquired by the pool.

    Registers the pgvector type adapter so that python lists / np arrays
    can be passed as vector parameters and results come back as np arrays.
    """
    await register_vector_async(conn)


async def init_pool() -> None:
    """Initialize the global async connection pool. Called once at startup."""
    global _pool
    if _pool is not None:
        return
    _pool = AsyncConnectionPool(
        conninfo=settings.database_url,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        configure=_configure_connection,
        open=False,
    )
    await _pool.open()


async def close_pool() -> None:
    """Close the connection pool. Called once at shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_connection() -> AsyncIterable[AsyncConnection]:
    """Acquire a connection from the pool (async context manager)."""
    if _pool is None:
        raise RuntimeError("Connection pool not initialized - call init_pool() first")
    async with _pool.connection() as conn:
        yield conn