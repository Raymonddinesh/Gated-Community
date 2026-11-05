"""Phase 17 Event Concurrency Helpers."""

import hashlib
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def acquire_event_number_lock(session: AsyncSession, society_id: UUID) -> None:
    """Acquire PostgreSQL transaction-level advisory lock for event number generation."""
    lock_id = int(hashlib.sha256(f"event_number_{society_id}".encode()).hexdigest()[:8], 16) - (1 << 31)
    bind = session.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})


async def acquire_event_capacity_lock(session: AsyncSession, event_id: UUID) -> None:
    """Acquire PostgreSQL transaction-level advisory lock for event registration & capacity checks."""
    lock_id = int(hashlib.sha256(f"event_capacity_{event_id}".encode()).hexdigest()[:8], 16) - (1 << 31)
    bind = session.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})
