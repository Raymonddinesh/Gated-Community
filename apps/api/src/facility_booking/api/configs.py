"""Facility Booking Config and Availability Windows API Router."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import require_permission, resolve_society_context
from apps.api.src.database.session import get_db_session
from apps.api.src.facility_booking.booking_service import FacilityBookingService
from apps.api.src.facility_booking.schemas import (
    FacilityAvailabilityWindowCreate,
    FacilityAvailabilityWindowResponse,
    FacilityBookingConfigCreate,
    FacilityBookingConfigResponse,
    FacilityBookingConfigUpdate,
)

router = APIRouter(prefix="/facilities", tags=["Facility Booking Configs"])


@router.get(
    "/{facility_id}/booking-config",
    response_model=FacilityBookingConfigResponse,
    dependencies=[Depends(require_permission("facility.booking.view"))],
)
async def get_booking_config(
    facility_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = FacilityBookingService(db)
    return await service.get_or_create_config(society_id, facility_id)


@router.put(
    "/{facility_id}/booking-config",
    response_model=FacilityBookingConfigResponse,
    dependencies=[Depends(require_permission("facility.booking.manage_rules"))],
)
async def upsert_booking_config(
    facility_id: UUID,
    payload: FacilityBookingConfigCreate | FacilityBookingConfigUpdate,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = FacilityBookingService(db)
    return await service.upsert_config(society_id, facility_id, payload)


@router.get(
    "/{facility_id}/availability-windows",
    response_model=list[FacilityAvailabilityWindowResponse],
    dependencies=[Depends(require_permission("facility.booking.view"))],
)
async def get_availability_windows(
    facility_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = FacilityBookingService(db)
    return await service.get_availability_windows(society_id, facility_id)


@router.put(
    "/{facility_id}/availability-windows",
    response_model=list[FacilityAvailabilityWindowResponse],
    dependencies=[Depends(require_permission("facility.booking.manage_availability"))],
)
async def set_availability_windows(
    facility_id: UUID,
    payload: list[FacilityAvailabilityWindowCreate],
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = FacilityBookingService(db)
    return await service.set_availability_windows(society_id, facility_id, payload)
