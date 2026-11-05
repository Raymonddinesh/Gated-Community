"""Phase 16 Security, Multi-Tenant RLS & Financial Isolation Finalization Test Suite."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.announcements.announcement_service import AnnouncementService
from apps.api.src.announcements.enums import AudienceType
from apps.api.src.announcements.exceptions import (
    AnnouncementNotFoundError,
    CrossTenantAudienceError,
)
from apps.api.src.announcements.schemas import (
    AnnouncementAudienceCreate,
    AnnouncementCreate,
)
from apps.api.src.database.models.billing import Invoice
from apps.api.src.database.models.finance import JournalEntry


@pytest.mark.asyncio
async def test_cross_tenant_audience_targeting_rejected(seeded_session: AsyncSession):
    service = AnnouncementService(seeded_session)
    society_id = uuid.uuid4()
    foreign_block_id = uuid.uuid4()
    author_id = uuid.uuid4()

    # Attempting audience targeting using a foreign block_id -> raises CrossTenantAudienceError
    with pytest.raises(CrossTenantAudienceError):
        await service.create_announcement(
            society_id,
            author_id,
            AnnouncementCreate(
                title="Cross Tenant Notice",
                body="Test body",
                audiences=[
                    AnnouncementAudienceCreate(
                        audience_type=AudienceType.BLOCK,
                        target_block_id=foreign_block_id,
                    )
                ],
            ),
        )


@pytest.mark.asyncio
async def test_multi_tenant_announcement_isolation(seeded_session: AsyncSession):
    service = AnnouncementService(seeded_session)
    society_a_id = uuid.uuid4()
    society_b_id = uuid.uuid4()
    author_id = uuid.uuid4()

    ann = await service.create_announcement(
        society_a_id,
        author_id,
        AnnouncementCreate(
            title="Society A Internal Notice",
            body="Confidential society A info.",
        ),
    )
    await service.publish_announcement(society_a_id, ann.id, author_id)

    # Attempting to fetch Society A's announcement with Society B's tenant context -> raises AnnouncementNotFoundError
    with pytest.raises(AnnouncementNotFoundError):
        await service.get_announcement(society_b_id, ann.id, author_id)


@pytest.mark.asyncio
async def test_announcements_financial_isolation(seeded_session: AsyncSession):
    """Assert zero mutations on financial / billing core database entities."""
    service = AnnouncementService(seeded_session)
    society_id = uuid.uuid4()
    author_id = uuid.uuid4()
    resident_id = uuid.uuid4()

    inv_count_before = (await seeded_session.execute(select(Invoice))).scalars().all()
    je_count_before = (await seeded_session.execute(select(JournalEntry))).scalars().all()

    # Perform announcement operations: create, publish, read, acknowledge
    ann = await service.create_announcement(
        society_id,
        author_id,
        AnnouncementCreate(
            title="Financial Isolation Notice",
            body="Zero accounting impact.",
            requires_acknowledgement=True,
        ),
    )
    await service.publish_announcement(society_id, ann.id, author_id)
    await service.mark_as_read(society_id, ann.id, resident_id)
    await service.acknowledge_announcement(society_id, ann.id, resident_id)

    inv_count_after = (await seeded_session.execute(select(Invoice))).scalars().all()
    je_count_after = (await seeded_session.execute(select(JournalEntry))).scalars().all()

    assert len(inv_count_before) == len(inv_count_after)
    assert len(je_count_before) == len(je_count_after)
