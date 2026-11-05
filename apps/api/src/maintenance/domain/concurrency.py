"""Transaction-safe Concurrency Lock Utilities for Maintenance Work Order Numbering."""

import hashlib
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def get_work_order_number_lock_key(society_id: uuid.UUID, year: int) -> int:
    """Generate a deterministic 64-bit integer lock key for pg_advisory_xact_lock."""
    digest = hashlib.sha256(f"wo_number_{society_id}_{year}".encode()).digest()
    lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
    return lock_key


async def acquire_work_order_number_lock(session: AsyncSession, society_id: uuid.UUID, year: int) -> None:
    """Acquire transaction-scoped advisory lock for work order sequence generation."""
    lock_key = get_work_order_number_lock_key(society_id, year)
    bind = session.bind
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": lock_key},
        )
