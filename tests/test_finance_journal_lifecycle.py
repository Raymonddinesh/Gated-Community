"""Tests for Journal Entry Lifecycle, Immutability, and Balanced Reversal."""

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.finance.application.journal_service import JournalService
from apps.api.src.finance.domain.exceptions import (
    DuplicateReversalException,
    ImmutableRecordException,
)
from apps.api.src.finance.infrastructure.repositories import (
    AccountRepository,
    JournalRepository,
    PeriodRepository,
)

SOCIETY_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER_ADMIN_ID = UUID("22222222-2222-2222-2222-22222222222a")


@pytest.mark.asyncio
async def test_journal_posting_and_immutability(seeded_session: AsyncSession) -> None:
    """A draft journal can be posted; once posted, it becomes immutable and cannot be re-posted."""
    service = JournalService(seeded_session)
    period_repo = PeriodRepository(seeded_session)
    account_repo = AccountRepository(seeded_session)

    period = await period_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 7, 1))
    bank_acc = await account_repo.get_by_code(SOCIETY_A_ID, "1010")
    income_acc = await account_repo.get_by_code(SOCIETY_A_ID, "4000")
    assert period is not None and bank_acc is not None and income_acc is not None

    lines = [
        {"account_id": bank_acc.id, "debit_amount": Decimal("2500.0000"), "credit_amount": Decimal("0.0000")},
        {
            "account_id": income_acc.id,
            "debit_amount": Decimal("0.0000"),
            "credit_amount": Decimal("2500.0000"),
        },
    ]

    # 1. Create draft
    draft = await service.create_draft_journal(
        society_id=SOCIETY_A_ID,
        financial_period_id=period.id,
        entry_date=date(2026, 7, 1),
        description="Hall Booking Income",
        lines_data=lines,
        created_by=USER_ADMIN_ID,
    )
    assert draft.status == "DRAFT"
    assert draft.posted_at is None

    # 2. Post journal
    posted = await service.post_journal(
        society_id=SOCIETY_A_ID,
        journal_id=draft.id,
        posted_by=USER_ADMIN_ID,
    )
    assert posted.status == "POSTED"
    assert posted.posted_at is not None
    assert posted.posted_by == USER_ADMIN_ID

    # 3. Attempting to re-post raises ImmutableRecordException
    with pytest.raises(ImmutableRecordException):
        await service.post_journal(
            society_id=SOCIETY_A_ID,
            journal_id=posted.id,
            posted_by=USER_ADMIN_ID,
        )


@pytest.mark.asyncio
async def test_balanced_reversal_creates_mirror_entry(seeded_session: AsyncSession) -> None:
    """Reversing a posted entry creates a new balanced reversal journal with inverted debits/credits."""
    service = JournalService(seeded_session)
    period_repo = PeriodRepository(seeded_session)
    account_repo = AccountRepository(seeded_session)
    journal_repo = JournalRepository(seeded_session)

    period = await period_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 7, 1))
    bank_acc = await account_repo.get_by_code(SOCIETY_A_ID, "1010")
    income_acc = await account_repo.get_by_code(SOCIETY_A_ID, "4000")
    assert period is not None and bank_acc is not None and income_acc is not None

    lines = [
        {"account_id": bank_acc.id, "debit_amount": Decimal("3000.0000"), "credit_amount": Decimal("0.0000")},
        {
            "account_id": income_acc.id,
            "debit_amount": Decimal("0.0000"),
            "credit_amount": Decimal("3000.0000"),
        },
    ]

    # Create & Post
    draft = await service.create_draft_journal(
        society_id=SOCIETY_A_ID,
        financial_period_id=period.id,
        entry_date=date(2026, 7, 1),
        description="Original Entry for Reversal",
        lines_data=lines,
        created_by=USER_ADMIN_ID,
    )
    posted = await service.post_journal(society_id=SOCIETY_A_ID, journal_id=draft.id, posted_by=USER_ADMIN_ID)

    # Reverse entry
    reversal = await service.reverse_journal(
        society_id=SOCIETY_A_ID,
        journal_id=posted.id,
        reason="Entered in error by accountant",
        reversed_by=USER_ADMIN_ID,
    )

    # Check reversal journal properties
    assert reversal.status == "POSTED"
    assert reversal.source_type == "REVERSAL"
    assert reversal.reversed_entry_id == posted.id
    assert reversal.total_debit == Decimal("3000.0000")
    assert reversal.total_credit == Decimal("3000.0000")

    # Reload reversal with lines
    rev_loaded = await journal_repo.get_by_id(reversal.id, SOCIETY_A_ID)
    assert rev_loaded is not None
    assert len(rev_loaded.lines) == 2

    # In original: Bank had Debit 3000, Income had Credit 3000
    # In reversal: Bank should have Credit 3000, Income should have Debit 3000
    for line in rev_loaded.lines:
        if line.account_id == bank_acc.id:
            assert line.credit_amount == Decimal("3000.0000")
            assert line.debit_amount == Decimal("0.0000")
        elif line.account_id == income_acc.id:
            assert line.debit_amount == Decimal("3000.0000")
            assert line.credit_amount == Decimal("0.0000")

    # Check original entry status updated to REVERSED
    orig_loaded = await journal_repo.get_by_id(posted.id, SOCIETY_A_ID)
    assert orig_loaded is not None
    assert orig_loaded.status == "REVERSED"
    assert orig_loaded.reversal_reason == "Entered in error by accountant"

    # 4. Attempting to reverse an already reversed journal raises DuplicateReversalException
    with pytest.raises(DuplicateReversalException):
        await service.reverse_journal(
            society_id=SOCIETY_A_ID,
            journal_id=posted.id,
            reason="Second reversal attempt",
            reversed_by=USER_ADMIN_ID,
        )
