"""Staff Concurrency and Lock Helpers."""

import zlib
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def generate_staff_advisory_lock_id(society_id: UUID, year: int) -> int:
    """Generate a deterministic 64-bit integer lock ID from society_id and year."""
    seed_str = f"staff_code_{society_id}_{year}"
    crc = zlib.crc32(seed_str.encode("utf-8")) & 0xFFFFFFFF
    return (crc << 32) | (year & 0xFFFFFFFF)


async def acquire_staff_code_lock(session: AsyncSession, society_id: UUID, year: int) -> None:
    """Acquire transaction-level PostgreSQL advisory lock for safe sequential staff code generation."""
    lock_id = generate_staff_advisory_lock_id(society_id, year)
    bind = session.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": lock_id},
        )
