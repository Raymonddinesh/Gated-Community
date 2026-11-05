"""Phase 19 Incident Management Concurrency Control."""

import hashlib
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def acquire_incident_number_lock(session: AsyncSession, society_id: UUID) -> None:
    """Acquire transaction-level advisory lock for incident number generation (INC-YYYY-XXXXXX)."""
    lock_id = int(hashlib.sha256(f"incident_number_{society_id}".encode()).hexdigest()[:8], 16) - (1 << 31)
    bind = session.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})


async def acquire_incident_triage_lock(session: AsyncSession, incident_id: UUID) -> None:
    """Acquire transaction-level advisory lock for incident triage & state changes."""
    lock_id = int(hashlib.sha256(f"incident_triage_{incident_id}".encode()).hexdigest()[:8], 16) - (1 << 31)
    bind = session.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})
