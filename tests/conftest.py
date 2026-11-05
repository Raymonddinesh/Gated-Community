"""Pytest fixtures and test environment configuration."""

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Set testing environment before importing app settings
os.environ["APP_ENV"] = "testing"
os.environ["DEBUG"] = "false"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-at-least-32-chars-long"
os.environ["RABBITMQ_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from apps.api.src.auth.security.rate_limiter import clear_in_memory_rate_limits
from apps.api.src.core.config import get_settings
from apps.api.src.database.base import Base
from apps.api.src.database.session import get_db_session
from apps.api.src.main import app
from infrastructure.scripts.seed_dev_data import seed_data


@pytest.fixture(autouse=True)
def reset_rate_limits():
    clear_in_memory_rate_limits()
    yield
    clear_in_memory_rate_limits()


@pytest.fixture(scope="session")
def test_settings():
    """Return test settings."""
    return get_settings()


@pytest_asyncio.fixture(scope="function")
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create a persistent in-memory SQLite AsyncEngine for test isolation."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Yield an active AsyncSession attached to the isolated test database."""
    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        autoflush=False,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def seeded_session(db_session: AsyncSession) -> AsyncSession:
    """Yield a database session pre-populated with deterministic seed data."""
    await seed_data(db_session)
    return db_session


@pytest_asyncio.fixture(scope="function")
async def async_client(seeded_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Yield an async test client with database session dependency overridden."""

    async def _override_get_db_session():
        yield seeded_session

    app.dependency_overrides[get_db_session] = _override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.pop(get_db_session, None)
