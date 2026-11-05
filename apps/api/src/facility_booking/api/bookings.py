"""Facility Booking Management Core API Router."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission, resolve_society_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.facility_booking.booking_service import FacilityBookingService
from apps.api.src.facility_booking.enums import BookingStatus
from apps.api.src.facility_booking.schemas import (
    FacilityBookingApprovalRequest,
    FacilityBookingCancellationRequest,
    FacilityBookingCreate,
    FacilityBookingListResponse,
    FacilityBookingResponse,
    FacilityBookingStatusHistoryResponse,
)

router = APIRouter(prefix="/facility-bookings", tags=["Facility Bookings"])


@router.post(
    "",
    response_model=FacilityBookingResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("facility.booking.create"))],
)
async def create_booking(
    payload: FacilityBookingCreate,
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = FacilityBookingService(db)
    return await service.create_booking(society_id, current_user.id, payload)


@router.get(
    "",
    response_model=FacilityBookingListResponse,
    dependencies=[Depends(require_permission("facility.booking.view"))],
)
async def list_bookings(
    facility_id: UUID | None = Query(None),
    user_id: UUID | None = Query(None),
    status: BookingStatus | None = Query(None),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = FacilityBookingService(db)
    items, total = await service.list_bookings(
        society_id=society_id,
        facility_id=facility_id,
        user_id=user_id,
        status=status,
        start_date=start_date,
        end_date=end_date,
        page=page,
        size=size,
    )
    return FacilityBookingListResponse(
        items=[FacilityBookingResponse.model_validate(b) for b in items],
        total=total,
        page=page,
        size=size,
    )


@router.get(
    "/{booking_id}",
    response_model=FacilityBookingResponse,
    dependencies=[Depends(require_permission("facility.booking.view"))],
)
async def get_booking(
    booking_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = FacilityBookingService(db)
    return await service.get_booking(society_id, booking_id)


@router.post(
    "/{booking_id}/approve",
    response_model=FacilityBookingResponse,
    dependencies=[Depends(require_permission("facility.booking.approve"))],
)
async def approve_or_reject_booking(
    booking_id: UUID,
    payload: FacilityBookingApprovalRequest,
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = FacilityBookingService(db)
    return await service.approve_booking(
        society_id, booking_id, current_user.id, payload.decision, payload.reason
    )


@router.post(
    "/{booking_id}/cancel",
    response_model=FacilityBookingResponse,
    dependencies=[Depends(require_permission("facility.booking.cancel"))],
)
async def cancel_booking(
    booking_id: UUID,
    payload: FacilityBookingCancellationRequest,
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = FacilityBookingService(db)
    return await service.cancel_booking(
        society_id=society_id,
        booking_id=booking_id,
        cancelled_by_user_id=current_user.id,
        reason=payload.cancellation_reason,
        admin_override=payload.admin_override,
    )


@router.post(
    "/{booking_id}/check-in",
    response_model=FacilityBookingResponse,
    dependencies=[Depends(require_permission("facility.booking.checkin"))],
)
async def checkin_booking(
    booking_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = FacilityBookingService(db)
    return await service.update_booking_status(
        society_id, booking_id, current_user.id, BookingStatus.CHECKED_IN, "Checked in at facility"
    )


@router.post(
    "/{booking_id}/complete",
    response_model=FacilityBookingResponse,
    dependencies=[Depends(require_permission("facility.booking.complete"))],
)
async def complete_booking(
    booking_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = FacilityBookingService(db)
    return await service.update_booking_status(
        society_id, booking_id, current_user.id, BookingStatus.COMPLETED, "Booking session completed"
    )


@router.post(
    "/{booking_id}/no-show",
    response_model=FacilityBookingResponse,
    dependencies=[Depends(require_permission("facility.booking.no_show"))],
)
async def noshow_booking(
    booking_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = FacilityBookingService(db)
    return await service.update_booking_status(
        society_id, booking_id, current_user.id, BookingStatus.NO_SHOW, "User failed to check in"
    )


@router.get(
    "/{booking_id}/audit-trail",
    response_model=list[FacilityBookingStatusHistoryResponse],
    dependencies=[Depends(require_permission("facility.booking.audit.view"))],
)
async def get_booking_audit_trail(
    booking_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = FacilityBookingService(db)
    return await service.get_status_history(society_id, booking_id)
