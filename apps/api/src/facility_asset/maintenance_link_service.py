"""Phase 14 Asset & Facility Maintenance Link Service."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.facility_asset import AssetMaintenanceLink
from apps.api.src.facility_asset.repositories import AssetMaintenanceLinkRepository
from apps.api.src.facility_asset.schemas import AssetMaintenanceLinkCreate


class MaintenanceLinkService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AssetMaintenanceLinkRepository(db)

    async def create_link(
        self, society_id: UUID, user_id: UUID | None, payload: AssetMaintenanceLinkCreate
    ) -> AssetMaintenanceLink:
        link = AssetMaintenanceLink(
            society_id=society_id,
            asset_id=payload.asset_id,
            facility_id=payload.facility_id,
            work_order_id=payload.work_order_id,
            complaint_id=payload.complaint_id,
            link_type=payload.link_type.value,
            linked_by_user_id=user_id,
            notes=payload.notes,
        )
        return await self.repo.create(link)

    async def list_by_asset(self, society_id: UUID, asset_id: UUID) -> list[AssetMaintenanceLink]:
        return await self.repo.list_by_asset(society_id, asset_id)

    async def list_by_facility(self, society_id: UUID, facility_id: UUID) -> list[AssetMaintenanceLink]:
        return await self.repo.list_by_facility(society_id, facility_id)
