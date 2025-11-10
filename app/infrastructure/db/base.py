from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_engine_from_config, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, declared_attr

from app.core.config import get_settings


class Base(DeclarativeBase):
    @declared_attr.directive
    def __tablename__(cls) -> str:  # type: ignore[misc,override]
        return cls.__name__.lower()


def build_engine(overrides: dict | None = None) -> AsyncEngine:
    settings = get_settings()
    connect_args: dict[str, object] = {}

    config = {
        "sqlalchemy.url": settings.database_url,
        "sqlalchemy.echo": settings.is_dev,
        "sqlalchemy.pool_pre_ping": True,
        "sqlalchemy.pool_size": 5,
        "sqlalchemy.max_overflow": 5,
        **(overrides or {}),
    }
    return async_engine_from_config(config, prefix="sqlalchemy.")


engine: AsyncEngine = build_engine()
AsyncSessionMaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionMaker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()

