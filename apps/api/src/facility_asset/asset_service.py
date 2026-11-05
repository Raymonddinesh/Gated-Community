"""Phase 14 Asset Service."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.facility_asset import (
    Asset,
    AssetAssignmentHistory,
    AssetLocation,
    AssetStatusHistory,
)
from apps.api.src.facility_asset.concurrency import generate_asset_code
from apps.api.src.facility_asset.enums import AssetStatus
from apps.api.src.facility_asset.exceptions import AssetNotFoundError
from apps.api.src.facility_asset.repositories import (
    AssetAssignmentRepository,
    AssetCategoryRepository,
    AssetLocationRepository,
    AssetRepository,
    AssetStatusHistoryRepository,
)
from apps.api.src.facility_asset.schemas import (
    AssetAssignmentCreate,
    AssetCreate,
    AssetLocationMove,
    AssetStatusUpdate,
    AssetUpdate,
)
from apps.api.src.facility_asset.state_machine import validate_asset_status_transition


class AssetService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AssetRepository(db)
        self.cat_repo = AssetCategoryRepository(db)
        self.loc_repo = AssetLocationRepository(db)
        self.status_repo = AssetStatusHistoryRepository(db)
        self.assign_repo = AssetAssignmentRepository(db)

    async def create_asset(self, society_id: UUID, user_id: UUID | None, payload: AssetCreate) -> Asset:
        code = await generate_asset_code(self.db, society_id)
        asset = Asset(
            society_id=society_id,
            asset_code=code,
            name=payload.name,
            category_id=payload.category_id,
            facility_id=payload.facility_id,
            facility_area_id=payload.facility_area_id,
            serial_number=payload.serial_number,
            model_number=payload.model_number,
            manufacturer=payload.manufacturer,
            vendor_id=payload.vendor_id,
            purchase_date=payload.purchase_date,
            warranty_expiry_date=payload.warranty_expiry_date,
            status=AssetStatus.IN_SERVICE.value,
            criticality=payload.criticality.value,
            estimated_lifespan_months=payload.estimated_lifespan_months,
        )
        asset = await self.repo.create(asset)

        # Log initial location if specified
        if payload.facility_id or payload.facility_area_id:
            loc = AssetLocation(
                society_id=society_id,
                asset_id=asset.id,
                facility_id=payload.facility_id,
                facility_area_id=payload.facility_area_id,
                location_details="Initial registration location",
                moved_by_user_id=user_id,
                reason="Initial creation",
            )
            await self.loc_repo.create(loc)

        return asset

    async def get_asset(self, society_id: UUID, asset_id: UUID) -> Asset:
        asset = await self.repo.get_by_id(society_id, asset_id)
        if not asset:
            raise AssetNotFoundError(str(asset_id))
        return asset

    async def list_assets(
        self,
        society_id: UUID,
        category_id: UUID | None = None,
        facility_id: UUID | None = None,
        status: str | None = None,
        criticality: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[Asset], int]:
        skip = (page - 1) * size
        return await self.repo.list_assets(
            society_id,
            category_id=category_id,
            facility_id=facility_id,
            status=status,
            criticality=criticality,
            skip=skip,
            limit=size,
        )

    async def update_asset(self, society_id: UUID, asset_id: UUID, payload: AssetUpdate) -> Asset:
        asset = await self.get_asset(society_id, asset_id)
        if payload.name is not None:
            asset.name = payload.name
        if payload.category_id is not None:
            asset.category_id = payload.category_id
        if payload.facility_id is not None:
            asset.facility_id = payload.facility_id
        if payload.facility_area_id is not None:
            asset.facility_area_id = payload.facility_area_id
        if payload.serial_number is not None:
            asset.serial_number = payload.serial_number
        if payload.model_number is not None:
            asset.model_number = payload.model_number
        if payload.manufacturer is not None:
            asset.manufacturer = payload.manufacturer
        if payload.vendor_id is not None:
            asset.vendor_id = payload.vendor_id
        if payload.purchase_date is not None:
            asset.purchase_date = payload.purchase_date
        if payload.warranty_expiry_date is not None:
            asset.warranty_expiry_date = payload.warranty_expiry_date
        if payload.criticality is not None:
            asset.criticality = payload.criticality.value
        if payload.estimated_lifespan_months is not None:
            asset.estimated_lifespan_months = payload.estimated_lifespan_months

        await self.db.flush()
        return asset

    async def update_asset_status(
        self, society_id: UUID, user_id: UUID | None, asset_id: UUID, payload: AssetStatusUpdate
    ) -> Asset:
        asset = await self.get_asset(society_id, asset_id)
        current_status = AssetStatus(asset.status)
        validate_asset_status_transition(current_status, payload.status)

        old_val = asset.status
        new_val = payload.status.value
        asset.status = new_val

        # Log status change history
        history = AssetStatusHistory(
            society_id=society_id,
            asset_id=asset_id,
            old_status=old_val,
            new_status=new_val,
            changed_by_user_id=user_id,
            reason=payload.reason,
        )
        await self.status_repo.create(history)

        await self.db.flush()
        return asset

    async def move_asset_location(
        self, society_id: UUID, user_id: UUID | None, asset_id: UUID, payload: AssetLocationMove
    ) -> AssetLocation:
        asset = await self.get_asset(society_id, asset_id)
        asset.facility_id = payload.facility_id
        asset.facility_area_id = payload.facility_area_id

        loc = AssetLocation(
            society_id=society_id,
            asset_id=asset_id,
            facility_id=payload.facility_id,
            facility_area_id=payload.facility_area_id,
            location_details=payload.location_details,
            moved_by_user_id=user_id,
            reason=payload.reason,
        )
        await self.loc_repo.create(loc)
        await self.db.flush()
        return loc

    async def assign_asset(
        self, society_id: UUID, user_id: UUID | None, asset_id: UUID, payload: AssetAssignmentCreate
    ) -> AssetAssignmentHistory:
        await self.get_asset(society_id, asset_id)

        assign = AssetAssignmentHistory(
            society_id=society_id,
            asset_id=asset_id,
            assigned_to_type=payload.assigned_to_type.value,
            assigned_staff_id=payload.assigned_staff_id,
            assigned_vendor_id=payload.assigned_vendor_id,
            assigned_by_user_id=user_id,
            notes=payload.notes,
        )
        return await self.assign_repo.create(assign)

    async def get_location_history(self, society_id: UUID, asset_id: UUID) -> list[AssetLocation]:
        await self.get_asset(society_id, asset_id)
        return await self.loc_repo.list_by_asset(society_id, asset_id)

    async def get_status_history(self, society_id: UUID, asset_id: UUID) -> list[AssetStatusHistory]:
        await self.get_asset(society_id, asset_id)
        return await self.status_repo.list_by_asset(society_id, asset_id)

    async def get_assignment_history(self, society_id: UUID, asset_id: UUID) -> list[AssetAssignmentHistory]:
        await self.get_asset(society_id, asset_id)
        return await self.assign_repo.list_by_asset(society_id, asset_id)
