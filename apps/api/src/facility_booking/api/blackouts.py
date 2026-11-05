"""Facility Blackout Period API Router."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission, resolve_society_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.facility_booking.booking_service import FacilityBookingService
from apps.api.src.facility_booking.enums import BlackoutStatus
from apps.api.src.facility_booking.schemas import (
    FacilityBlackoutPeriodCreate,
    FacilityBlackoutPeriodResponse,
)

router = APIRouter(prefix="/facilities", tags=["Facility Blackout Periods"])


@router.post(
    "/{facility_id}/blackouts",
    response_model=FacilityBlackoutPeriodResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("facility.booking.manage_blackout"))],
)
async def create_blackout(
    facility_id: UUID,
    payload: FacilityBlackoutPeriodCreate,
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = FacilityBookingService(db)
    return await service.create_blackout(society_id, facility_id, current_user.id, payload)


@router.get(
    "/{facility_id}/blackouts",
    response_model=list[FacilityBlackoutPeriodResponse],
    dependencies=[Depends(require_permission("facility.booking.view"))],
)
async def list_blackouts(
    facility_id: UUID,
    status: BlackoutStatus | None = Query(None),
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = FacilityBookingService(db)
    return await service.list_blackouts(society_id, facility_id, status)


@router.post(
    "/{facility_id}/blackouts/{blackout_id}/cancel",
    response_model=FacilityBlackoutPeriodResponse,
    dependencies=[Depends(require_permission("facility.booking.manage_blackout"))],
)
async def cancel_blackout(
    facility_id: UUID,
    blackout_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = FacilityBookingService(db)
    return await service.cancel_blackout(society_id, facility_id, blackout_id)
