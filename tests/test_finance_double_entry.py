"""Tests for Double-Entry Accounting Invariants and Validations."""

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.finance.application.journal_service import JournalService
from apps.api.src.finance.domain.exceptions import (
    InvalidJournalLinesException,
    UnbalancedJournalException,
)
from apps.api.src.finance.infrastructure.repositories import (
    AccountRepository,
    PeriodRepository,
)

SOCIETY_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest.mark.asyncio
async def test_unbalanced_journal_rejected(seeded_session: AsyncSession) -> None:
    """An unbalanced journal entry (Total Debits != Total Credits) must be rejected."""
    service = JournalService(seeded_session)
    period_repo = PeriodRepository(seeded_session)
    account_repo = AccountRepository(seeded_session)

    period = await period_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 5, 1))
    assert period is not None

    bank_acc = await account_repo.get_by_code(SOCIETY_A_ID, "1010")
    income_acc = await account_repo.get_by_code(SOCIETY_A_ID, "4000")
    assert bank_acc is not None and income_acc is not None

    unbalanced_lines = [
        {"account_id": bank_acc.id, "debit_amount": Decimal("1000.0000"), "credit_amount": Decimal("0.0000")},
        {
            "account_id": income_acc.id,
            "debit_amount": Decimal("0.0000"),
            "credit_amount": Decimal("950.0000"),
        },
    ]

    with pytest.raises(UnbalancedJournalException):
        await service.create_draft_journal(
            society_id=SOCIETY_A_ID,
            financial_period_id=period.id,
            entry_date=date(2026, 5, 1),
            description="Unbalanced Test Entry",
            lines_data=unbalanced_lines,
        )


@pytest.mark.asyncio
async def test_journal_requires_at_least_two_lines(seeded_session: AsyncSession) -> None:
    """A journal entry with fewer than 2 lines must be rejected."""
    service = JournalService(seeded_session)
    period_repo = PeriodRepository(seeded_session)
    account_repo = AccountRepository(seeded_session)

    period = await period_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 5, 1))
    bank_acc = await account_repo.get_by_code(SOCIETY_A_ID, "1010")
    assert period is not None and bank_acc is not None

    single_line = [
        {"account_id": bank_acc.id, "debit_amount": Decimal("1000.0000"), "credit_amount": Decimal("0.0000")}
    ]

    with pytest.raises(InvalidJournalLinesException):
        await service.create_draft_journal(
            society_id=SOCIETY_A_ID,
            financial_period_id=period.id,
            entry_date=date(2026, 5, 1),
            description="Single Line Journal",
            lines_data=single_line,
        )


@pytest.mark.asyncio
async def test_line_with_both_debit_and_credit_rejected(seeded_session: AsyncSession) -> None:
    """A single journal line cannot have both positive debit and positive credit."""
    service = JournalService(seeded_session)
    period_repo = PeriodRepository(seeded_session)
    account_repo = AccountRepository(seeded_session)

    period = await period_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 5, 1))
    bank_acc = await account_repo.get_by_code(SOCIETY_A_ID, "1010")
    income_acc = await account_repo.get_by_code(SOCIETY_A_ID, "4000")
    assert period is not None and bank_acc is not None and income_acc is not None

    invalid_lines = [
        {"account_id": bank_acc.id, "debit_amount": Decimal("100.0000"), "credit_amount": Decimal("50.0000")},
        {"account_id": income_acc.id, "debit_amount": Decimal("0.0000"), "credit_amount": Decimal("50.0000")},
    ]

    with pytest.raises(InvalidJournalLinesException):
        await service.create_draft_journal(
            society_id=SOCIETY_A_ID,
            financial_period_id=period.id,
            entry_date=date(2026, 5, 1),
            description="Invalid Line Format",
            lines_data=invalid_lines,
        )


@pytest.mark.asyncio
async def test_negative_amounts_rejected(seeded_session: AsyncSession) -> None:
    """Negative debit or credit amounts must be strictly rejected."""
    service = JournalService(seeded_session)
    period_repo = PeriodRepository(seeded_session)
    account_repo = AccountRepository(seeded_session)

    period = await period_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 5, 1))
    bank_acc = await account_repo.get_by_code(SOCIETY_A_ID, "1010")
    income_acc = await account_repo.get_by_code(SOCIETY_A_ID, "4000")
    assert period is not None and bank_acc is not None and income_acc is not None

    negative_lines = [
        {"account_id": bank_acc.id, "debit_amount": Decimal("-100.0000"), "credit_amount": Decimal("0.0000")},
        {
            "account_id": income_acc.id,
            "debit_amount": Decimal("0.0000"),
            "credit_amount": Decimal("-100.0000"),
        },
    ]

    with pytest.raises(InvalidJournalLinesException):
        await service.create_draft_journal(
            society_id=SOCIETY_A_ID,
            financial_period_id=period.id,
            entry_date=date(2026, 5, 1),
            description="Negative amounts test",
            lines_data=negative_lines,
        )


@pytest.mark.asyncio
async def test_decimal_precision_retains_exact_cents(seeded_session: AsyncSession) -> None:
    """Verify that monetary amounts retain 4-decimal exact precision with zero float truncation."""
    service = JournalService(seeded_session)
    period_repo = PeriodRepository(seeded_session)
    account_repo = AccountRepository(seeded_session)

    period = await period_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 5, 1))
    bank_acc = await account_repo.get_by_code(SOCIETY_A_ID, "1010")
    income_acc = await account_repo.get_by_code(SOCIETY_A_ID, "4000")
    assert period is not None and bank_acc is not None and income_acc is not None

    exact_amount = Decimal("12345.6789")
    balanced_lines = [
        {"account_id": bank_acc.id, "debit_amount": exact_amount, "credit_amount": Decimal("0.0000")},
        {"account_id": income_acc.id, "debit_amount": Decimal("0.0000"), "credit_amount": exact_amount},
    ]

    journal = await service.create_draft_journal(
        society_id=SOCIETY_A_ID,
        financial_period_id=period.id,
        entry_date=date(2026, 5, 1),
        description="Precise Decimal Test",
        lines_data=balanced_lines,
    )

    assert journal.total_debit == exact_amount
    assert journal.total_credit == exact_amount
    assert len(journal.lines) == 2
    assert journal.lines[0].debit_amount == exact_amount
    assert journal.lines[1].credit_amount == exact_amount
