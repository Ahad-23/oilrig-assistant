import pytest
import pytest_asyncio
import asyncpg
from src.config import settings

@pytest_asyncio.fixture(scope="function")
async def db_conn():
    """Provides an isolated asyncpg connection wrapped in a rolled-back transaction per test function."""
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT
    )
    tr = conn.transaction()
    await tr.start()
    try:
        yield conn
    finally:
        await tr.rollback()
        await conn.close()
