"""Phase 14 Facility Service."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.facility_asset import Facility, FacilityArea
from apps.api.src.facility_asset.concurrency import generate_facility_code
from apps.api.src.facility_asset.enums import FacilityStatus
from apps.api.src.facility_asset.exceptions import FacilityNotFoundError
from apps.api.src.facility_asset.repositories import FacilityRepository
from apps.api.src.facility_asset.schemas import (
    FacilityAreaCreate,
    FacilityCreate,
    FacilityStatusUpdate,
    FacilityUpdate,
)
from apps.api.src.facility_asset.state_machine import validate_facility_status_transition


class FacilityService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = FacilityRepository(db)

    async def create_facility(self, society_id: UUID, payload: FacilityCreate) -> Facility:
        code = await generate_facility_code(self.db, society_id)
        facility = Facility(
            society_id=society_id,
            facility_code=code,
            name=payload.name,
            facility_type=payload.facility_type.value,
            description=payload.description,
            status=FacilityStatus.ACTIVE.value,
            capacity=payload.capacity,
            location_summary=payload.location_summary,
            is_bookable_separately=payload.is_bookable_separately,
        )
        facility = await self.repo.create(facility)

        for area_data in payload.areas:
            area = FacilityArea(
                society_id=society_id,
                facility_id=facility.id,
                area_code=area_data.area_code,
                name=area_data.name,
                description=area_data.description,
                floor_level=area_data.floor_level,
                max_occupancy=area_data.max_occupancy,
                status="ACTIVE",
            )
            await self.repo.create_area(area)

        # Refresh facility with areas
        refreshed = await self.repo.get_by_id(society_id, facility.id)
        return refreshed or facility

    async def get_facility(self, society_id: UUID, facility_id: UUID) -> Facility:
        facility = await self.repo.get_by_id(society_id, facility_id)
        if not facility:
            raise FacilityNotFoundError(str(facility_id))
        return facility

    async def list_facilities(
        self,
        society_id: UUID,
        facility_type: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[Facility], int]:
        skip = (page - 1) * size
        return await self.repo.list_facilities(
            society_id, facility_type=facility_type, status=status, skip=skip, limit=size
        )

    async def update_facility(self, society_id: UUID, facility_id: UUID, payload: FacilityUpdate) -> Facility:
        facility = await self.get_facility(society_id, facility_id)
        if payload.name is not None:
            facility.name = payload.name
        if payload.facility_type is not None:
            facility.facility_type = payload.facility_type.value
        if payload.description is not None:
            facility.description = payload.description
        if payload.capacity is not None:
            facility.capacity = payload.capacity
        if payload.location_summary is not None:
            facility.location_summary = payload.location_summary
        if payload.is_bookable_separately is not None:
            facility.is_bookable_separately = payload.is_bookable_separately

        await self.db.flush()
        return facility

    async def update_facility_status(
        self, society_id: UUID, facility_id: UUID, payload: FacilityStatusUpdate
    ) -> Facility:
        facility = await self.get_facility(society_id, facility_id)
        current_status = FacilityStatus(facility.status)
        validate_facility_status_transition(current_status, payload.status)

        facility.status = payload.status.value
        await self.db.flush()
        return facility

    async def add_facility_area(
        self, society_id: UUID, facility_id: UUID, payload: FacilityAreaCreate
    ) -> FacilityArea:
        await self.get_facility(society_id, facility_id)
        area = FacilityArea(
            society_id=society_id,
            facility_id=facility_id,
            area_code=payload.area_code,
            name=payload.name,
            description=payload.description,
            floor_level=payload.floor_level,
            max_occupancy=payload.max_occupancy,
            status="ACTIVE",
        )
        return await self.repo.create_area(area)
