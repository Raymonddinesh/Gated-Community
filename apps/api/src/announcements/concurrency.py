"""Phase 16 Announcement Concurrency & Advisory Lock Control."""

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.announcements import Announcement


async def acquire_announcement_code_lock(db: AsyncSession, society_id: UUID) -> None:
    """Acquire transaction-level advisory lock on society ID for sequential announcement code generation."""
    lock_id = int(hashlib.sha256(f"announcement_code_{society_id}".encode()).hexdigest()[:8], 16) - (1 << 31)

    bind = db.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": lock_id},
        )


async def generate_announcement_number(db: AsyncSession, society_id: UUID) -> str:
    """Generate deterministic, lock-protected sequential announcement number (ANN-YYYY-XXXXXX)."""
    await acquire_announcement_code_lock(db, society_id)
    current_year = datetime.now(UTC).year
    prefix = f"ANN-{current_year}-"

    stmt = (
        select(func.count(Announcement.id))
        .where(Announcement.society_id == society_id)
        .where(Announcement.announcement_number.like(f"{prefix}%"))
    )
    count = (await db.scalar(stmt)) or 0
    seq = count + 1

    return f"{prefix}{seq:06d}"
