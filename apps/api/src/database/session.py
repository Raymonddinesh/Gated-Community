"""Async Database Engine and Session Management with Connection-Pooling-Safe Tenant Context."""

import logging
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from apps.api.src.core.config import get_settings
from apps.api.src.core.tenant_context import get_current_tenant_id

logger = logging.getLogger("societysphere.database")

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create singleton async database engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        engine_kwargs: dict[str, Any] = {
            "echo": settings.DEBUG,
            "pool_pre_ping": True,
        }
        if not settings.DATABASE_URL.startswith("sqlite"):
            engine_kwargs["pool_size"] = settings.DATABASE_POOL_SIZE
            engine_kwargs["max_overflow"] = settings.DATABASE_MAX_OVERFLOW
            engine_kwargs["pool_timeout"] = settings.DATABASE_POOL_TIMEOUT

        _engine = create_async_engine(
            settings.DATABASE_URL,
            **engine_kwargs,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create sessionmaker factory."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            autoflush=False,
            expire_on_commit=False,
        )
    return _session_factory


async def set_db_tenant_context(session: AsyncSession, society_id: UUID | None) -> None:
    """
    Safely configure PostgreSQL transaction-scoped tenant context.
    Uses PostgreSQL set_config with is_local=true.
    Because is_local is true, it is strictly scoped to the current transaction
    and automatically discards upon transaction commit, rollback, or connection return.
    This guarantees zero state leakage across connection pool reuses.
    """
    bind = session.bind
    # Only execute on PostgreSQL engines
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        val = str(society_id) if society_id else ""
        await session.execute(
            text("SELECT set_config('app.current_society_id', :val, true)"),
            {"val": val},
        )


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency yielding an async database session per request.
    Automatically applies active tenant context if present in task context.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            active_tenant = get_current_tenant_id()
            if active_tenant:
                await set_db_tenant_context(session, active_tenant)

            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_database_health() -> bool:
    """Execute a lightweight health probe to verify database connectivity."""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception as exc:
        logger.warning(f"Database health probe failed: {exc}")
        return False


async def init_db() -> None:
    """Initialize database engine at application startup."""
    try:
        engine = get_engine()
        logger.info(f"Database engine initialized for {engine.url.render_as_string(hide_password=True)}")
    except Exception as exc:
        logger.error(f"Failed to initialize database engine: {exc}")


async def close_db() -> None:
    """Dispose database engine connections at application shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        logger.info("Disposing database connection pool...")
        await _engine.dispose()
        _engine = None
        _session_factory = None
