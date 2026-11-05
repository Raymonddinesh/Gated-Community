"""Phase 15 Security, Multi-Tenant RLS & Concurrency Domain Finalization Test Suite."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.billing import Invoice
from apps.api.src.database.models.facility_asset import Facility
from apps.api.src.database.models.finance import JournalEntry
from apps.api.src.facility_booking.booking_service import FacilityBookingService
from apps.api.src.facility_booking.enums import BookingStatus
from apps.api.src.facility_booking.exceptions import (
    BookingNotFoundError,
    BookingSlotConflictError,
)
from apps.api.src.facility_booking.schemas import (
    FacilityBookingConfigCreate,
    FacilityBookingCreate,
)


@pytest.mark.asyncio
async def test_double_booking_prevention(seeded_session: AsyncSession):
    service = FacilityBookingService(seeded_session)
    society_id = uuid.uuid4()
    resident_user_id = uuid.uuid4()

    facility = Facility(
        society_id=society_id,
        facility_code="FAC-CONCUR-01",
        name="Badminton Court 1",
        facility_type="SPORTS",
        status="ACTIVE",
        capacity=4,
        is_bookable_separately=True,
    )
    seeded_session.add(facility)
    await seeded_session.flush()

    # Set direct approval
    await service.upsert_config(
        society_id,
        facility.id,
        FacilityBookingConfigCreate(is_bookable=True, requires_approval=False),
    )

    now = datetime.now(UTC)
    start_at = now + timedelta(days=5, hours=14)
    end_at = start_at + timedelta(hours=1)

    # 1. Create first booking -> succeeds
    b1 = await service.create_booking(
        society_id,
        resident_user_id,
        FacilityBookingCreate(
            facility_id=facility.id,
            title="Single Match 1",
            start_at=start_at,
            end_at=end_at,
            participant_count=2,
        ),
    )
    assert b1.status == BookingStatus.APPROVED.value

    # 2. Attempt duplicate overlapping booking -> fails with BookingSlotConflictError
    with pytest.raises(BookingSlotConflictError):
        await service.create_booking(
            society_id,
            resident_user_id,
            FacilityBookingCreate(
                facility_id=facility.id,
                title="Single Match 2 (Conflicting)",
                start_at=start_at + timedelta(minutes=30),
                end_at=end_at + timedelta(minutes=30),
                participant_count=2,
            ),
        )


@pytest.mark.asyncio
async def test_multi_tenant_isolation(seeded_session: AsyncSession):
    service = FacilityBookingService(seeded_session)
    society_id = uuid.uuid4()
    resident_user_id = uuid.uuid4()

    # 1. Create booking in society
    facility = Facility(
        society_id=society_id,
        facility_code="FAC-RLS-01",
        name="Community Garden",
        facility_type="OUTDOOR",
        status="ACTIVE",
        capacity=50,
        is_bookable_separately=True,
    )
    seeded_session.add(facility)
    await seeded_session.flush()

    now = datetime.now(UTC)
    b = await service.create_booking(
        society_id,
        resident_user_id,
        FacilityBookingCreate(
            facility_id=facility.id,
            title="Gardening Club",
            start_at=now + timedelta(days=4),
            end_at=now + timedelta(days=4, hours=2),
            participant_count=10,
        ),
    )

    # 2. Other society ID
    other_society_id = uuid.uuid4()

    # 3. Attempt accessing b.id using other_society_id -> raises BookingNotFoundError
    with pytest.raises(BookingNotFoundError):
        await service.get_booking(other_society_id, b.id)


@pytest.mark.asyncio
async def test_financial_isolation(seeded_session: AsyncSession):
    """Verify Phase 15 creates zero direct mutations on Financial / Billing core tables."""
    service = FacilityBookingService(seeded_session)
    society_id = uuid.uuid4()
    resident_user_id = uuid.uuid4()

    facility = Facility(
        society_id=society_id,
        facility_code="FAC-FIN-01",
        name="Roof Top Deck",
        facility_type="CLUBHOUSE",
        status="ACTIVE",
        capacity=50,
        is_bookable_separately=True,
    )
    seeded_session.add(facility)
    await seeded_session.flush()

    # Count initial invoices and journal entries
    inv_count_before = (await seeded_session.execute(select(Invoice))).scalars().all()
    je_count_before = (await seeded_session.execute(select(JournalEntry))).scalars().all()

    now = datetime.now(UTC)
    await service.create_booking(
        society_id,
        resident_user_id,
        FacilityBookingCreate(
            facility_id=facility.id,
            title="Sunset Stargazing",
            start_at=now + timedelta(days=6),
            end_at=now + timedelta(days=6, hours=3),
            participant_count=15,
        ),
    )

    inv_count_after = (await seeded_session.execute(select(Invoice))).scalars().all()
    je_count_after = (await seeded_session.execute(select(JournalEntry))).scalars().all()

    # Verify zero financial side-effects
    assert len(inv_count_before) == len(inv_count_after)
    assert len(je_count_before) == len(je_count_after)
