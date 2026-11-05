"""Phase 16 Announcements Functional & Lifecycle Unit Test Suite."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.announcements.announcement_service import AnnouncementService
from apps.api.src.announcements.enums import (
    AnnouncementPriority,
    AnnouncementStatus,
)
from apps.api.src.announcements.exceptions import (
    AlreadyAcknowledgedError,
    InvalidAnnouncementStateError,
)
from apps.api.src.announcements.schemas import (
    AnnouncementCreate,
    AnnouncementUpdate,
)


@pytest.mark.asyncio
async def test_announcement_creation_and_numbering(seeded_session: AsyncSession):
    service = AnnouncementService(seeded_session)
    society_id = uuid.uuid4()
    author_id = uuid.uuid4()

    ann = await service.create_announcement(
        society_id,
        author_id,
        AnnouncementCreate(
            title="General Notice",
            summary="Test Summary",
            body="Test announcement body content.",
            priority=AnnouncementPriority.NORMAL,
        ),
    )

    assert ann.announcement_number.startswith("ANN-")
    assert ann.status == AnnouncementStatus.DRAFT.value
    assert ann.version_number == 1


@pytest.mark.asyncio
async def test_announcement_lifecycle_and_approval_workflow(seeded_session: AsyncSession):
    service = AnnouncementService(seeded_session)
    society_id = uuid.uuid4()
    author_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    # 1. Create draft
    ann = await service.create_announcement(
        society_id,
        author_id,
        AnnouncementCreate(
            title="Important Water Interruption",
            body="Water supply will be paused.",
            priority=AnnouncementPriority.IMPORTANT,
        ),
    )
    assert ann.status == AnnouncementStatus.DRAFT.value

    # 2. Submit for review
    submitted = await service.submit_announcement(society_id, ann.id, author_id)
    assert submitted.status == AnnouncementStatus.PENDING_REVIEW.value

    # 3. Approve
    approved = await service.approve_announcement(society_id, ann.id, admin_id, "Approved for broadcast")
    assert approved.status == AnnouncementStatus.APPROVED.value

    # 4. Publish
    published = await service.publish_announcement(society_id, ann.id, admin_id)
    assert published.status == AnnouncementStatus.PUBLISHED.value
    assert published.published_at is not None

    # 5. Invalid transition from PUBLISHED to PENDING_REVIEW -> raises InvalidAnnouncementStateError
    with pytest.raises(InvalidAnnouncementStateError):
        await service.submit_announcement(society_id, ann.id, author_id)


@pytest.mark.asyncio
async def test_read_receipts_and_mandatory_acknowledgement(seeded_session: AsyncSession):
    service = AnnouncementService(seeded_session)
    society_id = uuid.uuid4()
    author_id = uuid.uuid4()
    resident_id = uuid.uuid4()

    # Create published announcement requiring acknowledgement
    ann = await service.create_announcement(
        society_id,
        author_id,
        AnnouncementCreate(
            title="Mandatory Evacuation Drill",
            body="Fire safety drill on Saturday.",
            priority=AnnouncementPriority.URGENT,
            requires_acknowledgement=True,
        ),
    )
    await service.publish_announcement(society_id, ann.id, author_id)

    # 1. Mark read
    await service.mark_as_read(society_id, ann.id, resident_id)
    read_obj = await service.read_repo.get_user_read(society_id, ann.id, resident_id)
    assert read_obj is not None

    # 2. Acknowledge
    ack = await service.acknowledge_announcement(society_id, ann.id, resident_id)
    assert ack.version_number == 1

    # 3. Duplicate acknowledgement -> raises AlreadyAcknowledgedError
    with pytest.raises(AlreadyAcknowledgedError):
        await service.acknowledge_announcement(society_id, ann.id, resident_id)


@pytest.mark.asyncio
async def test_published_announcement_versioning(seeded_session: AsyncSession):
    service = AnnouncementService(seeded_session)
    society_id = uuid.uuid4()
    author_id = uuid.uuid4()

    ann = await service.create_announcement(
        society_id,
        author_id,
        AnnouncementCreate(
            title="AGM Date Announcement",
            body="AGM on Oct 20.",
            priority=AnnouncementPriority.NORMAL,
        ),
    )
    await service.publish_announcement(society_id, ann.id, author_id)
    assert ann.version_number == 1

    # Update body after publication -> creates version 1 snapshot and increments version_number to 2
    updated = await service.update_announcement(
        society_id,
        ann.id,
        author_id,
        AnnouncementUpdate(body="Correction: AGM on Oct 25 at 10 AM.", edit_reason="Date corrected"),
    )

    assert updated.version_number == 2
    versions = await service.version_repo.list_by_announcement(society_id, ann.id)
    assert len(versions) == 1
    assert versions[0].version_number == 1
