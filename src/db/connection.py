import asyncpg
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.config import settings

# SQLAlchemy Async Engine
engine = create_async_engine(
    settings.async_database_url,
    echo=False,
    pool_size=10,
    max_overflow=20
)

async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession
)

async def get_db_session() -> AsyncSession:
    """Dependency for providing an async database session."""
    async with async_session_factory() as session:
        yield session

async def get_raw_asyncpg_connection() -> asyncpg.Connection:
    """Direct asyncpg connection for high-throughput bulk operations."""
    return await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT
    )

async def init_db() -> None:
    """Executes the DDL schema to prepare the database tables and indexes."""
    schema_path = Path(__file__).resolve().parent / "schema.sql"
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn = await get_raw_asyncpg_connection()
    try:
        await conn.execute(schema_sql)
    finally:
        await conn.close()
