"""Phase 17 Events & Community Management Functional Unit Test Suite."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.events.enums import (
    EventAttendanceStatus,
    EventRegistrationStatus,
    EventStatus,
    EventType,
    ParticipantType,
)
from apps.api.src.events.event_service import EventService
from apps.api.src.events.exceptions import (
    DuplicateRegistrationError,
    InvalidEventStateError,
)
from apps.api.src.events.schemas import (
    EventAttachmentCreate,
    EventCreate,
    EventRegistrationCreate,
)


@pytest.mark.asyncio
async def test_event_creation_and_numbering(seeded_session: AsyncSession):
    service = EventService(seeded_session)
    society_id = uuid.uuid4()
    creator_id = uuid.uuid4()

    starts = datetime.now(UTC) + timedelta(days=5)
    ends = starts + timedelta(hours=3)

    event = await service.create_event(
        society_id,
        creator_id,
        EventCreate(
            title="Society Cultural Fest 2026",
            description="Annual cultural festival with music, dance, and food stalls.",
            event_type=EventType.CULTURAL,
            capacity=100,
            registration_required=True,
            starts_at=starts,
            ends_at=ends,
        ),
    )

    assert event.event_number.startswith("EVT-")
    assert event.status == EventStatus.DRAFT.value
    assert event.capacity == 100
    assert event.title == "Society Cultural Fest 2026"


@pytest.mark.asyncio
async def test_event_lifecycle_and_approval_workflow(seeded_session: AsyncSession):
    service = EventService(seeded_session)
    society_id = uuid.uuid4()
    creator_id = uuid.uuid4()
    approver_id = uuid.uuid4()

    starts = datetime.now(UTC) + timedelta(days=2)
    ends = starts + timedelta(hours=2)

    # 1. Create Draft
    event = await service.create_event(
        society_id,
        creator_id,
        EventCreate(
            title="Badminton Tournament",
            description="Inter-block badminton doubles tournament.",
            event_type=EventType.SPORTS,
            capacity=20,
            starts_at=starts,
            ends_at=ends,
        ),
    )
    assert event.status == EventStatus.DRAFT.value

    # 2. Submit
    submitted = await service.submit_event(society_id, event.id, creator_id)
    assert submitted.status == EventStatus.PENDING_APPROVAL.value

    # 3. Approve
    approved = await service.approve_event(society_id, event.id, approver_id, "Approved by committee")
    assert approved.status == EventStatus.APPROVED.value

    # 4. Publish
    published = await service.publish_event(society_id, event.id, approver_id)
    assert published.status in {EventStatus.PUBLISHED.value, EventStatus.REGISTRATION_OPEN.value}

    # 5. Invalid transition from PUBLISHED to PENDING_APPROVAL -> raises InvalidEventStateError
    with pytest.raises(InvalidEventStateError):
        await service.submit_event(society_id, event.id, creator_id)


@pytest.mark.asyncio
async def test_event_registration_and_waitlist(seeded_session: AsyncSession):
    service = EventService(seeded_session)
    society_id = uuid.uuid4()
    creator_id = uuid.uuid4()
    user1_id = uuid.uuid4()
    user2_id = uuid.uuid4()
    user3_id = uuid.uuid4()

    starts = datetime.now(UTC) + timedelta(days=3)
    ends = starts + timedelta(hours=2)

    # Create event with capacity = 2
    event = await service.create_event(
        society_id,
        creator_id,
        EventCreate(
            title="Limited Capacity Workshop",
            description="Yoga and wellness workshop.",
            event_type=EventType.WORKSHOP,
            capacity=2,
            registration_required=True,
            starts_at=starts,
            ends_at=ends,
        ),
    )
    await service.publish_event(society_id, event.id, creator_id)

    # Register user 1 -> CONFIRMED
    reg1 = await service.register_participant(
        society_id, event.id, user1_id, EventRegistrationCreate(participant_type=ParticipantType.RESIDENT)
    )
    assert reg1.status == EventRegistrationStatus.CONFIRMED.value

    # Register user 2 -> CONFIRMED
    reg2 = await service.register_participant(
        society_id, event.id, user2_id, EventRegistrationCreate(participant_type=ParticipantType.RESIDENT)
    )
    assert reg2.status == EventRegistrationStatus.CONFIRMED.value

    # Register user 3 -> WAITLISTED (capacity full)
    reg3 = await service.register_participant(
        society_id, event.id, user3_id, EventRegistrationCreate(participant_type=ParticipantType.RESIDENT)
    )
    assert reg3.status == EventRegistrationStatus.WAITLISTED.value
    assert reg3.waitlist_position == 1

    # Duplicate registration attempt by user1 -> raises DuplicateRegistrationError
    with pytest.raises(DuplicateRegistrationError):
        await service.register_participant(
            society_id, event.id, user1_id, EventRegistrationCreate(participant_type=ParticipantType.RESIDENT)
        )


@pytest.mark.asyncio
async def test_event_attendance_tracking(seeded_session: AsyncSession):
    service = EventService(seeded_session)
    society_id = uuid.uuid4()
    creator_id = uuid.uuid4()
    user_id = uuid.uuid4()

    starts = datetime.now(UTC) + timedelta(days=1)
    ends = starts + timedelta(hours=2)

    event = await service.create_event(
        society_id,
        creator_id,
        EventCreate(
            title="Tree Plantation Drive",
            description="Green initiative in society park.",
            event_type=EventType.COMMUNITY,
            capacity=50,
            starts_at=starts,
            ends_at=ends,
        ),
    )
    await service.publish_event(society_id, event.id, creator_id)
    await service.register_participant(
        society_id, event.id, user_id, EventRegistrationCreate(participant_type=ParticipantType.RESIDENT)
    )

    # Record attendance check-in
    att = await service.record_attendance(
        society_id, event.id, user_id, creator_id, EventAttendanceStatus.CHECKED_IN, "Arrived at 9 AM"
    )
    assert att.status == EventAttendanceStatus.CHECKED_IN.value
    assert att.check_in_time is not None


@pytest.mark.asyncio
async def test_event_attachment_security(seeded_session: AsyncSession):
    service = EventService(seeded_session)
    society_id = uuid.uuid4()
    creator_id = uuid.uuid4()

    starts = datetime.now(UTC) + timedelta(days=5)
    ends = starts + timedelta(hours=2)

    event = await service.create_event(
        society_id,
        creator_id,
        EventCreate(
            title="Diwali Gala Night",
            description="Diwali fireworks and dinner.",
            event_type=EventType.FESTIVAL,
            starts_at=starts,
            ends_at=ends,
        ),
    )

    attachment = await service.add_attachment(
        society_id,
        event.id,
        creator_id,
        EventAttachmentCreate(
            file_name="diwali_poster.png",
            file_size=500000,
            mime_type="image/png",
        ),
    )

    assert attachment.file_name == "diwali_poster.png"
    assert "events/" in attachment.storage_object_key
