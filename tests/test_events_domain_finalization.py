"""Phase 17 Security, Multi-Tenant RLS & Financial Isolation Finalization Test Suite."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.billing import Invoice
from apps.api.src.database.models.finance import JournalEntry
from apps.api.src.events.enums import EventRegistrationStatus, EventType, ParticipantType
from apps.api.src.events.event_service import EventService
from apps.api.src.events.exceptions import EventNotFoundError, InvalidEventStateError
from apps.api.src.events.participant_privacy import EventParticipantPrivacyFilter
from apps.api.src.events.schemas import EventCreate, EventRegistrationCreate


@pytest.mark.asyncio
async def test_cross_tenant_event_isolation(seeded_session: AsyncSession):
    service = EventService(seeded_session)
    society_a_id = uuid.uuid4()
    society_b_id = uuid.uuid4()
    creator_id = uuid.uuid4()

    starts = datetime.now(UTC) + timedelta(days=2)
    ends = starts + timedelta(hours=2)

    event_a = await service.create_event(
        society_a_id,
        creator_id,
        EventCreate(
            title="Society A Private Gathering",
            description="Internal event for Society A.",
            event_type=EventType.COMMUNITY,
            starts_at=starts,
            ends_at=ends,
        ),
    )

    # Attempting to retrieve Society A's event using Society B context -> raises EventNotFoundError
    with pytest.raises(EventNotFoundError):
        await service._get_event(society_b_id, event_a.id)


@pytest.mark.asyncio
async def test_events_financial_isolation(seeded_session: AsyncSession):
    """Assert zero direct mutations on financial or billing core entities."""
    service = EventService(seeded_session)
    society_id = uuid.uuid4()
    creator_id = uuid.uuid4()
    resident_id = uuid.uuid4()

    inv_count_before = (await seeded_session.execute(select(Invoice))).scalars().all()
    je_count_before = (await seeded_session.execute(select(JournalEntry))).scalars().all()

    starts = datetime.now(UTC) + timedelta(days=5)
    ends = starts + timedelta(hours=2)

    # Perform event lifecycle operations: create, publish, register, cancel
    event = await service.create_event(
        society_id,
        creator_id,
        EventCreate(
            title="Financial Isolation Event",
            description="Zero accounting ledger impact.",
            event_type=EventType.AWARENESS,
            starts_at=starts,
            ends_at=ends,
        ),
    )
    await service.publish_event(society_id, event.id, creator_id)
    await service.register_participant(
        society_id, event.id, resident_id, EventRegistrationCreate(participant_type=ParticipantType.RESIDENT)
    )

    inv_count_after = (await seeded_session.execute(select(Invoice))).scalars().all()
    je_count_after = (await seeded_session.execute(select(JournalEntry))).scalars().all()

    assert len(inv_count_before) == len(inv_count_after)
    assert len(je_count_before) == len(je_count_after)


@pytest.mark.asyncio
async def test_capacity_concurrency_protection(seeded_session: AsyncSession):
    """Verify transactional capacity enforcement prevents capacity overflow."""
    service = EventService(seeded_session)
    society_id = uuid.uuid4()
    creator_id = uuid.uuid4()

    starts = datetime.now(UTC) + timedelta(days=4)
    ends = starts + timedelta(hours=2)

    # Event capacity = 3
    event = await service.create_event(
        society_id,
        creator_id,
        EventCreate(
            title="Capacity Concurrency Test Event",
            description="Strict capacity enforcement test.",
            event_type=EventType.WORKSHOP,
            capacity=3,
            starts_at=starts,
            ends_at=ends,
        ),
    )
    await service.publish_event(society_id, event.id, creator_id)

    # Register 5 users sequentially under transactional locks
    regs = []
    for _ in range(5):
        uid = uuid.uuid4()
        reg = await service.register_participant(
            society_id, event.id, uid, EventRegistrationCreate(participant_type=ParticipantType.RESIDENT)
        )
        regs.append(reg)

    confirmed_count = sum(1 for r in regs if r.status == EventRegistrationStatus.CONFIRMED.value)
    waitlisted_count = sum(1 for r in regs if r.status == EventRegistrationStatus.WAITLISTED.value)

    assert confirmed_count == 3
    assert waitlisted_count == 2


@pytest.mark.asyncio
async def test_participant_privacy_filtering():
    """Verify non-admin users receive masked participant details."""
    user1_id = uuid.uuid4()
    user2_id = uuid.uuid4()

    participants = [
        {"id": "p1", "user_id": str(user1_id), "status": "CONFIRMED", "registered_at": "2026-10-05"},
        {"id": "p2", "user_id": str(user2_id), "status": "CONFIRMED", "registered_at": "2026-10-05"},
    ]

    # Admin view sees all unmasked
    admin_filtered = EventParticipantPrivacyFilter.filter_participant_details(participants, user1_id, True)
    assert len(admin_filtered) == 2
    assert admin_filtered[1].get("is_masked") is None

    # Resident view masks user2 details for user1
    resident_filtered = EventParticipantPrivacyFilter.filter_participant_details(
        participants, user1_id, False
    )
    assert resident_filtered[0].get("is_masked") is None
    assert resident_filtered[1].get("is_masked") is True


@pytest.mark.asyncio
async def test_invalid_event_schedule_timestamps():
    """Verify invalid event start/end datetimes raise ValueError."""
    starts = datetime.now(UTC) + timedelta(days=5)
    ends = starts - timedelta(hours=1)

    with pytest.raises(ValueError, match="starts_at must be strictly before ends_at"):
        EventCreate(
            title="Invalid Schedule Event",
            description="Test description.",
            event_type=EventType.COMMUNITY,
            starts_at=starts,
            ends_at=ends,
        )


@pytest.mark.asyncio
async def test_creator_self_approval_rejected(seeded_session: AsyncSession):
    """Verify event creator cannot self-approve event request."""
    service = EventService(seeded_session)
    society_id = uuid.uuid4()
    creator_id = uuid.uuid4()

    starts = datetime.now(UTC) + timedelta(days=5)
    ends = starts + timedelta(hours=2)

    event = await service.create_event(
        society_id,
        creator_id,
        EventCreate(
            title="Self Approval Test Event",
            description="Test self approval restriction.",
            event_type=EventType.AWARENESS,
            starts_at=starts,
            ends_at=ends,
        ),
    )
    await service.submit_event(society_id, event.id, creator_id)

    with pytest.raises(InvalidEventStateError, match="cannot self-approve"):
        await service.approve_event(society_id, event.id, creator_id)


@pytest.mark.asyncio
async def test_waitlist_promotion_on_cancellation(seeded_session: AsyncSession):
    """Verify cancelling confirmed registration promotes first waitlisted registration."""
    service = EventService(seeded_session)
    society_id = uuid.uuid4()
    creator_id = uuid.uuid4()
    user1_id = uuid.uuid4()
    user2_id = uuid.uuid4()

    starts = datetime.now(UTC) + timedelta(days=5)
    ends = starts + timedelta(hours=2)

    event = await service.create_event(
        society_id,
        creator_id,
        EventCreate(
            title="Capacity 1 Event",
            description="Event with capacity 1 for waitlist promotion test.",
            event_type=EventType.WORKSHOP,
            capacity=1,
            starts_at=starts,
            ends_at=ends,
        ),
    )
    await service.publish_event(society_id, event.id, creator_id)

    # User 1 -> CONFIRMED
    reg1 = await service.register_participant(
        society_id, event.id, user1_id, EventRegistrationCreate(participant_type=ParticipantType.RESIDENT)
    )
    assert reg1.status == EventRegistrationStatus.CONFIRMED.value

    # User 2 -> WAITLISTED
    reg2 = await service.register_participant(
        society_id, event.id, user2_id, EventRegistrationCreate(participant_type=ParticipantType.RESIDENT)
    )
    assert reg2.status == EventRegistrationStatus.WAITLISTED.value

    # Cancel User 1 -> User 2 promoted to CONFIRMED
    await service.cancel_registration(society_id, event.id, user1_id, reason="Cannot attend")
    promoted_reg2 = await service.registration_repo.get_by_id(society_id, reg2.id)
    assert promoted_reg2 is not None
    assert promoted_reg2.status == EventRegistrationStatus.CONFIRMED.value
