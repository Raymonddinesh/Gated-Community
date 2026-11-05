"""Vendor Concurrency Control & Sequential Code Generator."""

import hashlib
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.vendor import VendorProfile


async def generate_vendor_code(db: AsyncSession, society_id: UUID) -> str:
    """Generate deterministic, sequential, lock-protected vendor code per society.

    Format: VND-YYYY-XXXXXX (e.g., VND-2026-000001)
    Uses pg_advisory_xact_lock on PostgreSQL to prevent concurrent code collisions.
    """
    lock_id = int(hashlib.sha256(f"vendor_code_{society_id}".encode()).hexdigest()[:8], 16) - (1 << 31)

    bind = db.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": lock_id},
        )

    current_year = datetime.utcnow().year
    prefix = f"VND-{current_year}-"

    stmt = (
        select(func.count(VendorProfile.id))
        .where(VendorProfile.society_id == society_id)
        .where(VendorProfile.vendor_code.like(f"{prefix}%"))
    )
    count = (await db.scalar(stmt)) or 0
    seq = count + 1

    return f"{prefix}{seq:06d}"
