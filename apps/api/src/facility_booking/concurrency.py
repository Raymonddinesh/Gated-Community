"""Facility Booking Concurrency Control & Advisory Locks."""

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.facility_booking import FacilityBooking


async def acquire_booking_code_lock(db: AsyncSession, society_id: UUID) -> None:
    """Acquire transaction-level advisory lock on society ID to serialize booking code sequence generation."""
    lock_id = int(hashlib.sha256(f"booking_code_{society_id}".encode()).hexdigest()[:8], 16) - (1 << 31)

    bind = db.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": lock_id},
        )


async def acquire_facility_slot_lock(db: AsyncSession, facility_id: UUID) -> None:
    """Acquire transaction-level advisory lock on facility ID to serialize concurrent reservation requests."""
    lock_id = int(hashlib.sha256(f"facility_res_{facility_id}".encode()).hexdigest()[:8], 16) - (1 << 31)

    bind = db.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": lock_id},
        )


# Backward compatibility aliases
acquire_facility_reservation_lock = acquire_facility_slot_lock


async def generate_booking_code(db: AsyncSession, society_id: UUID) -> str:
    """Generate deterministic, sequential, lock-protected booking code per society.

    Format: BK-YYYY-XXXXXX (e.g., BK-2026-000001)
    """
    await acquire_booking_code_lock(db, society_id)
    current_year = datetime.now(UTC).year
    prefix = f"BK-{current_year}-"

    stmt = (
        select(func.count(FacilityBooking.id))
        .where(FacilityBooking.society_id == society_id)
        .where(FacilityBooking.booking_code.like(f"{prefix}%"))
    )
    count = (await db.scalar(stmt)) or 0
    seq = count + 1

    return f"{prefix}{seq:06d}"
