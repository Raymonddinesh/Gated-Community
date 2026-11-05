"""Tests for Financial Period Lifecycle and Closed Period Posting Protection."""

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.finance.application.journal_service import JournalService
from apps.api.src.finance.application.period_service import PeriodService
from apps.api.src.finance.domain.exceptions import (
    ClosedPeriodPostingException,
    InvalidFinancialPeriodDateException,
)
from apps.api.src.finance.infrastructure.repositories import (
    AccountRepository,
    PeriodRepository,
)

SOCIETY_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER_ADMIN_ID = UUID("22222222-2222-2222-2222-22222222222a")


@pytest.mark.asyncio
async def test_posting_into_closed_period_blocked(seeded_session: AsyncSession) -> None:
    """Posting into a closed financial period must be rejected with ClosedPeriodPostingException."""
    period_service = PeriodService(seeded_session)
    journal_service = JournalService(seeded_session)
    period_repo = PeriodRepository(seeded_session)
    account_repo = AccountRepository(seeded_session)

    # 1. Get period and close it
    period = await period_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 6, 1))
    assert period is not None
    await period_service.close_period(
        society_id=SOCIETY_A_ID,
        period_id=period.id,
        closed_by=USER_ADMIN_ID,
        reason="Fiscal Year End Lock",
    )

    bank_acc = await account_repo.get_by_code(SOCIETY_A_ID, "1010")
    income_acc = await account_repo.get_by_code(SOCIETY_A_ID, "4000")
    assert bank_acc is not None and income_acc is not None

    lines = [
        {"account_id": bank_acc.id, "debit_amount": Decimal("500.0000"), "credit_amount": Decimal("0.0000")},
        {
            "account_id": income_acc.id,
            "debit_amount": Decimal("0.0000"),
            "credit_amount": Decimal("500.0000"),
        },
    ]

    # Attempt to post into closed period
    with pytest.raises(ClosedPeriodPostingException):
        await journal_service.create_draft_journal(
            society_id=SOCIETY_A_ID,
            financial_period_id=period.id,
            entry_date=date(2026, 6, 1),
            description="Attempted posting to closed period",
            lines_data=lines,
        )


@pytest.mark.asyncio
async def test_reopening_closed_period_allows_postings(seeded_session: AsyncSession) -> None:
    """A closed period can be reopened with audited justification, restoring posting capability."""
    period_service = PeriodService(seeded_session)
    journal_service = JournalService(seeded_session)
    period_repo = PeriodRepository(seeded_session)
    account_repo = AccountRepository(seeded_session)

    period = await period_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 6, 1))
    assert period is not None

    # Close period
    await period_service.close_period(SOCIETY_A_ID, period.id, closed_by=USER_ADMIN_ID, reason="Closing")

    # Reopen period
    await period_service.reopen_period(
        SOCIETY_A_ID,
        period.id,
        reopened_by=USER_ADMIN_ID,
        reason="Auditor adjustments authorized by AGM",
    )

    bank_acc = await account_repo.get_by_code(SOCIETY_A_ID, "1010")
    income_acc = await account_repo.get_by_code(SOCIETY_A_ID, "4000")
    assert bank_acc is not None and income_acc is not None

    lines = [
        {"account_id": bank_acc.id, "debit_amount": Decimal("500.0000"), "credit_amount": Decimal("0.0000")},
        {
            "account_id": income_acc.id,
            "debit_amount": Decimal("0.0000"),
            "credit_amount": Decimal("500.0000"),
        },
    ]

    journal = await journal_service.create_draft_journal(
        society_id=SOCIETY_A_ID,
        financial_period_id=period.id,
        entry_date=date(2026, 6, 1),
        description="Posting after reopening",
        lines_data=lines,
    )
    assert journal is not None
    assert journal.status == "DRAFT"


@pytest.mark.asyncio
async def test_entry_date_outside_period_range_rejected(seeded_session: AsyncSession) -> None:
    """An entry date that falls outside the period's start and end date boundaries is rejected."""
    journal_service = JournalService(seeded_session)
    period_repo = PeriodRepository(seeded_session)
    account_repo = AccountRepository(seeded_session)

    # FY 2026-2027 runs from 2026-04-01 to 2027-03-31
    period = await period_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 6, 1))
    assert period is not None

    bank_acc = await account_repo.get_by_code(SOCIETY_A_ID, "1010")
    income_acc = await account_repo.get_by_code(SOCIETY_A_ID, "4000")
    assert bank_acc is not None and income_acc is not None

    lines = [
        {"account_id": bank_acc.id, "debit_amount": Decimal("500.0000"), "credit_amount": Decimal("0.0000")},
        {
            "account_id": income_acc.id,
            "debit_amount": Decimal("0.0000"),
            "credit_amount": Decimal("500.0000"),
        },
    ]

    # Date from 2025 is outside FY 2026-2027
    with pytest.raises(InvalidFinancialPeriodDateException):
        await journal_service.create_draft_journal(
            society_id=SOCIETY_A_ID,
            financial_period_id=period.id,
            entry_date=date(2025, 12, 31),
            description="Prior year date",
            lines_data=lines,
        )
