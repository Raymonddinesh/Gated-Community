"""Facility & Asset Concurrency Control & Sequential Code Generators."""

import hashlib
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.facility_asset import Asset, Facility


async def generate_facility_code(db: AsyncSession, society_id: UUID) -> str:
    """Generate deterministic, sequential, lock-protected facility code per society.

    Format: FAC-YYYY-XXXXXX (e.g., FAC-2026-000001)
    """
    lock_id = int(hashlib.sha256(f"facility_code_{society_id}".encode()).hexdigest()[:8], 16) - (1 << 31)

    bind = db.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": lock_id},
        )

    current_year = datetime.utcnow().year
    prefix = f"FAC-{current_year}-"

    stmt = (
        select(func.count(Facility.id))
        .where(Facility.society_id == society_id)
        .where(Facility.facility_code.like(f"{prefix}%"))
    )
    count = (await db.scalar(stmt)) or 0
    seq = count + 1

    return f"{prefix}{seq:06d}"


async def generate_asset_code(db: AsyncSession, society_id: UUID) -> str:
    """Generate deterministic, sequential, lock-protected asset code per society.

    Format: AST-YYYY-XXXXXX (e.g., AST-2026-000001)
    """
    lock_id = int(hashlib.sha256(f"asset_code_{society_id}".encode()).hexdigest()[:8], 16) - (1 << 31)

    bind = db.get_bind()
    if bind and getattr(bind, "dialect", None) and bind.dialect.name == "postgresql":
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": lock_id},
        )

    current_year = datetime.utcnow().year
    prefix = f"AST-{current_year}-"

    stmt = (
        select(func.count(Asset.id))
        .where(Asset.society_id == society_id)
        .where(Asset.asset_code.like(f"{prefix}%"))
    )
    count = (await db.scalar(stmt)) or 0
    seq = count + 1

    return f"{prefix}{seq:06d}"
