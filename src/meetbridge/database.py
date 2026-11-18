from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from meetbridge.config import get_settings
from meetbridge.models import Base

settings = get_settings()

if settings.database_url.startswith("sqlite+"):
    database_path = settings.database_url.split("///", maxsplit=1)[-1]
    if database_path != ":memory:":
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=settings.app_env == "development" and settings.log_level.upper() == "DEBUG",
)
AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def create_database_schema() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionFactory() as session:
        yield session


async def dispose_database() -> None:
    await engine.dispose()
