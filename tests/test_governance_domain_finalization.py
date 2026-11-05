"""Phase 18 Governance Security, RLS, Privacy & Domain Finalization Test Suite."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.billing import Invoice, Payment
from apps.api.src.database.models.finance import JournalEntry
from apps.api.src.database.models.governance import (
    Committee,
    Meeting,
)
from apps.api.src.governance.enums import (
    CommitteeType,
    MeetingType,
)
from apps.api.src.governance.exceptions import GovernanceNotFoundError
from apps.api.src.governance.governance_service import GovernanceService
from apps.api.src.governance.schemas import (
    CommitteeCreate,
    MeetingCreate,
    ResolutionCreate,
)

UUID_SOCIETY_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
UUID_SOCIETY_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
UUID_USER_OWNER_A = uuid.UUID("22222222-2222-2222-2222-22222222222a")
UUID_USER_MEMBER_B = uuid.UUID("55555555-5555-5555-5555-55555555555b")
UUID_SUPER_ADMIN = uuid.UUID("11111111-1111-1111-1111-11111111111a")


@pytest.mark.asyncio
async def test_cross_tenant_governance_isolation(seeded_session: AsyncSession):
    """Verify that Society A cannot access or mutate Society B's governance entities."""
    service = GovernanceService(seeded_session)

    society_a = UUID_SOCIETY_A
    society_b = UUID_SOCIETY_B
    user_a = UUID_USER_OWNER_A

    # Create Committee in Society A
    committee_a = await service.create_committee(
        society_a,
        CommitteeCreate(
            name="Society A Executive Committee",
            committee_type=CommitteeType.MANAGING_COMMITTEE,
        ),
        creator_id=user_a,
    )

    # Create Meeting in Society A
    starts = datetime.now(UTC) + timedelta(days=2)
    ends = starts + timedelta(hours=2)
    meeting_a = await service.create_meeting(
        society_a,
        user_a,
        MeetingCreate(
            title="Society A General Meeting",
            meeting_type=MeetingType.GENERAL_BODY_MEETING,
            scheduled_start_at=starts,
            scheduled_end_at=ends,
        ),
    )

    # Society B listing committees should return empty list
    committees_b = await service.list_committees(society_b)
    assert len(committees_b) == 0

    # Society B listing meetings should return empty list
    meetings_b = await service.list_meetings(society_b)
    assert len(meetings_b) == 0

    # Society B fetching Society A's committee should raise GovernanceNotFoundError
    with pytest.raises(GovernanceNotFoundError):
        await service.get_committee(society_b, committee_a.id)

    # Society B fetching Society A's meeting should raise GovernanceNotFoundError
    with pytest.raises(GovernanceNotFoundError):
        await service.get_meeting(society_b, meeting_a.id)


@pytest.mark.asyncio
async def test_financial_ledger_isolation(seeded_session: AsyncSession):
    """Verify that governance operations perform 0 mutations or interactions with financial tables."""
    service = GovernanceService(seeded_session)
    society_id = UUID_SOCIETY_A
    user_id = UUID_USER_OWNER_A

    # Record baseline counts of financial tables
    res_journal = await seeded_session.execute(select(JournalEntry))
    baseline_journals = len(res_journal.scalars().all())

    res_invoice = await seeded_session.execute(select(Invoice))
    baseline_invoices = len(res_invoice.scalars().all())

    res_payment = await seeded_session.execute(select(Payment))
    baseline_payments = len(res_payment.scalars().all())

    # Execute complete governance workflow
    await service.create_committee(
        society_id,
        CommitteeCreate(
            name="Finance Sub-Committee",
            committee_type=CommitteeType.SUB_COMMITTEE,
        ),
        creator_id=user_id,
    )

    starts = datetime.now(UTC) + timedelta(days=1)
    ends = starts + timedelta(hours=2)
    meeting = await service.create_meeting(
        society_id,
        user_id,
        MeetingCreate(
            title="Budget Review Meeting",
            meeting_type=MeetingType.COMMITTEE_MEETING,
            scheduled_start_at=starts,
            scheduled_end_at=ends,
        ),
    )

    await service.create_resolution(
        society_id,
        user_id,
        ResolutionCreate(
            meeting_id=meeting.id,
            title="Approve Quarterly Expense Report",
            description="Resolution to adopt Q2 financial report.",
        ),
    )

    # Verify post-operation counts of financial tables match baseline EXACTLY
    res_journal_after = await seeded_session.execute(select(JournalEntry))
    after_journals = len(res_journal_after.scalars().all())

    res_invoice_after = await seeded_session.execute(select(Invoice))
    after_invoices = len(res_invoice_after.scalars().all())

    res_payment_after = await seeded_session.execute(select(Payment))
    after_payments = len(res_payment_after.scalars().all())

    assert baseline_journals == after_journals
    assert baseline_invoices == after_invoices
    assert baseline_payments == after_payments


@pytest.mark.asyncio
async def test_governance_entities_exist_in_db(seeded_session: AsyncSession):
    """Verify that all Phase 18 models are properly bound to SQLAlchemy metadata."""
    service = GovernanceService(seeded_session)
    society_id = UUID_SOCIETY_A
    user_id = UUID_USER_OWNER_A

    c = await service.create_committee(
        society_id,
        CommitteeCreate(
            name="Audit Committee",
            committee_type=CommitteeType.SUB_COMMITTEE,
        ),
        creator_id=user_id,
    )

    m = await service.create_meeting(
        society_id,
        user_id,
        MeetingCreate(
            title="Audit Meeting",
            meeting_type=MeetingType.COMMITTEE_MEETING,
            scheduled_start_at=datetime.now(UTC),
            scheduled_end_at=datetime.now(UTC) + timedelta(hours=1),
        ),
    )

    db_c = await seeded_session.execute(select(Committee).where(Committee.id == c.id))
    assert db_c.scalar_one_or_none() is not None

    db_m = await seeded_session.execute(select(Meeting).where(Meeting.id == m.id))
    assert db_m.scalar_one_or_none() is not None
