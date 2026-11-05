"""Phase 18 Governance Concurrency Control."""

import hashlib
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def acquire_meeting_number_lock(session: AsyncSession, society_id: UUID) -> None:
    """Acquire transaction-level advisory lock for meeting number generation."""
    lock_id = int(hashlib.sha256(f"meeting_number_{society_id}".encode()).hexdigest()[:8], 16) - (1 << 31)
    bind = session.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})


async def acquire_resolution_number_lock(session: AsyncSession, society_id: UUID) -> None:
    """Acquire transaction-level advisory lock for resolution number generation."""
    lock_id = int(hashlib.sha256(f"resolution_number_{society_id}".encode()).hexdigest()[:8], 16) - (1 << 31)
    bind = session.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})


async def acquire_resolution_vote_lock(session: AsyncSession, resolution_id: UUID) -> None:
    """Acquire transaction-level advisory lock for resolution voting concurrency."""
    lock_id = int(hashlib.sha256(f"resolution_vote_{resolution_id}".encode()).hexdigest()[:8], 16) - (1 << 31)
    bind = session.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})
