import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from confhub.config import get_settings
from confhub.models import Base

logger = logging.getLogger(__name__)

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine():
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        connect_args = {}
        if "sqlite" in settings.database_url:
            connect_args["check_same_thread"] = False
        _engine = create_async_engine(
            settings.database_url,
            connect_args=connect_args,
            echo=False,
        )
        _session_factory = async_sessionmaker(
            _engine, expire_on_commit=False, class_=AsyncSession
        )
    return _engine


class _LazySessionFactory:
    """Proxy that behaves like async_sessionmaker but initialises lazily."""

    def __call__(self, *args, **kwargs) -> AsyncSession:
        _get_engine()
        assert _session_factory is not None
        return _session_factory(*args, **kwargs)

    def __enter__(self):
        raise TypeError("Use 'async with' not 'with'")

    def __aiter__(self):
        raise TypeError("Not iterable")


# Module-level export used by cli.py and scheduler.py via `async with AsyncSessionFactory() as session`
AsyncSessionFactory = _LazySessionFactory()


async def create_database_schema() -> None:
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_database() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    _get_engine()
    assert _session_factory is not None
    async with _session_factory() as session:
        yield session
