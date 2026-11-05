"""Repository for Society and Physical Spatial Hierarchy."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.society import Block, Floor, Society, Unit


class SocietyRepository:
    """Data access layer for Society, Block, Floor, and Unit entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_society_by_id(self, society_id: UUID) -> Society | None:
        """Fetch society by primary key."""
        result = await self.session.execute(select(Society).where(Society.id == society_id))
        return result.scalar_one_or_none()

    async def list_societies(self, limit: int = 50, offset: int = 0) -> list[Society]:
        """List societies (platform-level)."""
        result = await self.session.execute(
            select(Society).where(Society.archived_at.is_(None)).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def get_blocks_for_society(self, society_id: UUID) -> list[Block]:
        """List blocks for a specific society."""
        result = await self.session.execute(
            select(Block)
            .where(Block.society_id == society_id, Block.archived_at.is_(None))
            .order_by(Block.sequence_order)
        )
        return list(result.scalars().all())

    async def get_block_by_id(self, block_id: UUID, society_id: UUID | None = None) -> Block | None:
        """Get block by ID with optional tenant check."""
        query = select(Block).where(Block.id == block_id, Block.archived_at.is_(None))
        if society_id:
            query = query.where(Block.society_id == society_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_floors_for_block(self, block_id: UUID, society_id: UUID | None = None) -> list[Floor]:
        """List floors within a block."""
        query = select(Floor).where(Floor.block_id == block_id, Floor.archived_at.is_(None))
        if society_id:
            query = query.where(Floor.society_id == society_id)
        result = await self.session.execute(query.order_by(Floor.sequence_order))
        return list(result.scalars().all())

    async def get_floor_by_id(self, floor_id: UUID, society_id: UUID | None = None) -> Floor | None:
        """Get floor by ID with optional tenant check."""
        query = select(Floor).where(Floor.id == floor_id, Floor.archived_at.is_(None))
        if society_id:
            query = query.where(Floor.society_id == society_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_units_for_floor(self, floor_id: UUID, society_id: UUID | None = None) -> list[Unit]:
        """List units on a floor."""
        query = select(Unit).where(Unit.floor_id == floor_id, Unit.archived_at.is_(None))
        if society_id:
            query = query.where(Unit.society_id == society_id)
        result = await self.session.execute(query.order_by(Unit.unit_number))
        return list(result.scalars().all())

    async def get_unit_by_id(self, unit_id: UUID, society_id: UUID | None = None) -> Unit | None:
        """Get unit by ID with optional tenant check."""
        query = select(Unit).where(Unit.id == unit_id, Unit.archived_at.is_(None))
        if society_id:
            query = query.where(Unit.society_id == society_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
