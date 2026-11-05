"""Phase 15 Facility Booking Functional & Lifecycle Unit Test Suite."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.facility_asset import Facility
from apps.api.src.facility_booking.booking_service import FacilityBookingService
from apps.api.src.facility_booking.enums import BlackoutStatus, BookingApprovalDecision, BookingStatus
from apps.api.src.facility_booking.exceptions import (
    FacilityBlackoutConflictError,
)
from apps.api.src.facility_booking.schemas import (
    FacilityAvailabilityWindowCreate,
    FacilityBlackoutPeriodCreate,
    FacilityBookingConfigCreate,
    FacilityBookingCreate,
    FacilityBookingParticipantCreate,
)


@pytest.mark.asyncio
async def test_facility_booking_config_and_windows(seeded_session: AsyncSession):
    service = FacilityBookingService(seeded_session)
    society_id = uuid.uuid4()

    # 1. Create a dummy facility
    facility = Facility(
        society_id=society_id,
        facility_code="FAC-TEST-01",
        name="Test Party Hall",
        facility_type="CLUBHOUSE",
        status="ACTIVE",
        capacity=100,
        is_bookable_separately=True,
    )
    seeded_session.add(facility)
    await seeded_session.flush()

    # 2. Get default config
    config = await service.get_or_create_config(society_id, facility.id)
    assert config.is_bookable is True
    assert config.requires_approval is False

    # 3. Update config
    updated_config = await service.upsert_config(
        society_id,
        facility.id,
        FacilityBookingConfigCreate(
            is_bookable=True,
            requires_approval=True,
            max_capacity=80,
            min_duration_minutes=60,
            max_duration_minutes=240,
            advance_booking_days=14,
            min_cancellation_notice_hours=12,
        ),
    )
    assert updated_config.requires_approval is True
    assert updated_config.max_capacity == 80

    # 4. Set availability windows (Monday to Sunday, 08:00 - 22:00)
    windows_payload = [
        FacilityAvailabilityWindowCreate(day_of_week=i, start_time="08:00", end_time="22:00", is_active=True)
        for i in range(7)
    ]
    windows = await service.set_availability_windows(society_id, facility.id, windows_payload)
    assert len(windows) == 7


@pytest.mark.asyncio
async def test_facility_blackout_periods(seeded_session: AsyncSession):
    service = FacilityBookingService(seeded_session)
    society_id = uuid.uuid4()
    admin_user_id = uuid.uuid4()

    facility = Facility(
        society_id=society_id,
        facility_code="FAC-TEST-02",
        name="Test Pool",
        facility_type="SWIMMING_POOL",
        status="ACTIVE",
        capacity=30,
        is_bookable_separately=True,
    )
    seeded_session.add(facility)
    await seeded_session.flush()

    now = datetime.now(UTC)
    start_at = now + timedelta(days=2, hours=10)
    end_at = start_at + timedelta(hours=4)

    # 1. Create blackout
    blackout = await service.create_blackout(
        society_id,
        facility.id,
        admin_user_id,
        FacilityBlackoutPeriodCreate(
            title="Pool Maintenance",
            start_at=start_at,
            end_at=end_at,
            reason="Chlorination and filter replacement",
        ),
    )
    assert blackout.status == BlackoutStatus.SCHEDULED.value

    # 2. Attempt booking overlapping blackout -> should raise FacilityBlackoutConflictError
    with pytest.raises(FacilityBlackoutConflictError):
        await service.create_booking(
            society_id,
            admin_user_id,
            FacilityBookingCreate(
                facility_id=facility.id,
                title="Swimmers Practice",
                start_at=start_at + timedelta(hours=1),
                end_at=start_at + timedelta(hours=2),
                participant_count=5,
            ),
        )

    # 3. Cancel blackout
    cancelled_blackout = await service.cancel_blackout(society_id, facility.id, blackout.id)
    assert cancelled_blackout.status == BlackoutStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_facility_booking_lifecycle_and_approvals(seeded_session: AsyncSession):
    service = FacilityBookingService(seeded_session)
    society_id = uuid.uuid4()
    admin_user_id = uuid.uuid4()
    resident_user_id = uuid.uuid4()

    facility = Facility(
        society_id=society_id,
        facility_code="FAC-TEST-03",
        name="Test Tennis Court",
        facility_type="SPORTS",
        status="ACTIVE",
        capacity=10,
        is_bookable_separately=True,
    )
    seeded_session.add(facility)
    await seeded_session.flush()

    # Require approval config
    await service.upsert_config(
        society_id,
        facility.id,
        FacilityBookingConfigCreate(
            is_bookable=True,
            requires_approval=True,
            min_duration_minutes=30,
            max_duration_minutes=120,
            advance_booking_days=30,
            min_cancellation_notice_hours=24,
        ),
    )

    now = datetime.now(UTC)
    start_at = now + timedelta(days=3, hours=10)
    end_at = start_at + timedelta(hours=1)

    # 1. Resident creates booking request -> status PENDING_APPROVAL
    booking = await service.create_booking(
        society_id,
        resident_user_id,
        FacilityBookingCreate(
            facility_id=facility.id,
            title="Weekend Tennis Match",
            start_at=start_at,
            end_at=end_at,
            participant_count=4,
            participants=[FacilityBookingParticipantCreate(name="Partner A", contact_phone="9998887771")],
        ),
    )
    assert booking.status == BookingStatus.PENDING_APPROVAL.value
    assert booking.booking_code.startswith("BK-")

    # 2. Admin approves booking
    approved_booking = await service.approve_booking(
        society_id,
        booking.id,
        admin_user_id,
        BookingApprovalDecision.APPROVED,
        "Approved for resident event",
    )
    assert approved_booking.status == BookingStatus.APPROVED.value

    # 3. Check-in
    checked_in_booking = await service.update_booking_status(
        society_id,
        booking.id,
        resident_user_id,
        BookingStatus.CHECKED_IN,
        "Arrived at tennis court",
    )
    assert checked_in_booking.status == BookingStatus.CHECKED_IN.value

    # 4. Complete
    completed_booking = await service.update_booking_status(
        society_id,
        booking.id,
        resident_user_id,
        BookingStatus.COMPLETED,
        "Session finished",
    )
    assert completed_booking.status == BookingStatus.COMPLETED.value

    # 5. Audit history length check
    history = await service.get_status_history(society_id, booking.id)
    assert len(history) >= 4
