"""Tests for Multi-Tenant Isolation in Financial Domain and Ledger Operations."""

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.finance.application.expense_service import ExpenseService
from apps.api.src.finance.application.journal_service import JournalService
from apps.api.src.finance.domain.exceptions import (
    CrossTenantFinancialException,
    InactiveAccountPostingException,
)
from apps.api.src.finance.infrastructure.repositories import (
    AccountRepository,
    JournalRepository,
    PeriodRepository,
)

SOCIETY_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SOCIETY_B_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.mark.asyncio
async def test_cross_tenant_account_usage_blocked(seeded_session: AsyncSession) -> None:
    """A journal entry in Society A cannot reference an account owned by Society B."""
    service = JournalService(seeded_session)
    period_repo = PeriodRepository(seeded_session)
    account_repo = AccountRepository(seeded_session)

    period_a = await period_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 8, 1))
    assert period_a is not None

    bank_acc_a = await account_repo.get_by_code(SOCIETY_A_ID, "1010")
    # Fetch account from Society B
    income_acc_b = await account_repo.get_by_code(SOCIETY_B_ID, "4000")
    assert bank_acc_a is not None and income_acc_b is not None

    # Mixed accounts: Bank from A, Income from B
    illegal_lines = [
        {
            "account_id": bank_acc_a.id,
            "debit_amount": Decimal("1000.0000"),
            "credit_amount": Decimal("0.0000"),
        },
        {
            "account_id": income_acc_b.id,
            "debit_amount": Decimal("0.0000"),
            "credit_amount": Decimal("1000.0000"),
        },
    ]

    with pytest.raises((CrossTenantFinancialException, InactiveAccountPostingException)):
        await service.create_draft_journal(
            society_id=SOCIETY_A_ID,
            financial_period_id=period_a.id,
            entry_date=date(2026, 8, 1),
            description="Cross tenant account leakage attempt",
            lines_data=illegal_lines,
        )


@pytest.mark.asyncio
async def test_cross_tenant_financial_period_blocked(seeded_session: AsyncSession) -> None:
    """Society A cannot post a journal entry into Society B's financial period."""
    service = JournalService(seeded_session)
    period_repo = PeriodRepository(seeded_session)
    account_repo = AccountRepository(seeded_session)

    # Fetch period belonging to Society B
    period_b = await period_repo.get_period_for_date(SOCIETY_B_ID, date(2026, 8, 1))
    assert period_b is not None

    bank_acc_a = await account_repo.get_by_code(SOCIETY_A_ID, "1010")
    income_acc_a = await account_repo.get_by_code(SOCIETY_A_ID, "4000")
    assert bank_acc_a is not None and income_acc_a is not None

    lines = [
        {
            "account_id": bank_acc_a.id,
            "debit_amount": Decimal("1000.0000"),
            "credit_amount": Decimal("0.0000"),
        },
        {
            "account_id": income_acc_a.id,
            "debit_amount": Decimal("0.0000"),
            "credit_amount": Decimal("1000.0000"),
        },
    ]

    with pytest.raises(CrossTenantFinancialException):
        await service.create_draft_journal(
            society_id=SOCIETY_A_ID,
            financial_period_id=period_b.id,  # Period belonging to Society B!
            entry_date=date(2026, 8, 1),
            description="Cross tenant period attempt",
            lines_data=lines,
        )


@pytest.mark.asyncio
async def test_cross_tenant_journal_queries_isolated(seeded_session: AsyncSession) -> None:
    """Querying journals for Society B returns zero records from Society A."""
    journal_repo = JournalRepository(seeded_session)

    # Society A has seeded journal JV-000001
    journals_a = await journal_repo.list_journals(SOCIETY_A_ID)
    assert len(journals_a) >= 1

    # Society B should have no journals from Society A
    journals_b = await journal_repo.list_journals(SOCIETY_B_ID)
    assert len(journals_b) == 0

    # Direct query by ID with wrong society returns None
    first_jv_id = journals_a[0].id
    leaked = await journal_repo.get_by_id(first_jv_id, society_id=SOCIETY_B_ID)
    assert leaked is None


@pytest.mark.asyncio
async def test_cross_tenant_expense_creation_blocked(seeded_session: AsyncSession) -> None:
    """An expense in Society A cannot use an expense or asset account belonging to Society B."""
    expense_service = ExpenseService(seeded_session)
    period_repo = PeriodRepository(seeded_session)
    account_repo = AccountRepository(seeded_session)

    period_a = await period_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 8, 1))
    assert period_a is not None

    # Account 5000 in Society B
    cat_b = await account_repo.get_by_code(SOCIETY_B_ID, "5000")
    paid_a = await account_repo.get_by_code(SOCIETY_A_ID, "1010")
    assert cat_b is not None and paid_a is not None

    with pytest.raises(CrossTenantFinancialException):
        await expense_service.create_expense(
            society_id=SOCIETY_A_ID,
            financial_period_id=period_a.id,
            expense_date=date(2026, 8, 1),
            category_account_id=cat_b.id,  # From Society B!
            paid_from_account_id=paid_a.id,
            description="Cross tenant expense test",
            amount=Decimal("500.0000"),
        )
