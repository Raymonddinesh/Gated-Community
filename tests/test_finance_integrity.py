"""Tests for Society-Wide Financial Ledger Integrity Invariants."""

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.finance import JournalEntry, JournalEntryLine
from apps.api.src.finance.application.expense_service import ExpenseService
from apps.api.src.finance.application.journal_service import JournalService
from apps.api.src.finance.domain.models import quantize_amount
from apps.api.src.finance.infrastructure.repositories import (
    AccountRepository,
    PeriodRepository,
)

SOCIETY_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER_ADMIN_ID = UUID("22222222-2222-2222-2222-22222222222a")


@pytest.mark.asyncio
async def test_society_wide_double_entry_integrity_invariant(seeded_session: AsyncSession) -> None:
    """Invariant: SUM(debits) must exactly equal SUM(credits) across ALL posted records in the society."""
    journal_service = JournalService(seeded_session)
    expense_service = ExpenseService(seeded_session)
    period_repo = PeriodRepository(seeded_session)
    account_repo = AccountRepository(seeded_session)

    period = await period_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 6, 1))
    assert period is not None

    bank_acc = await account_repo.get_by_code(SOCIETY_A_ID, "1010")
    income_acc = await account_repo.get_by_code(SOCIETY_A_ID, "4000")
    exp_acc = await account_repo.get_by_code(SOCIETY_A_ID, "5020")
    assert bank_acc is not None and income_acc is not None and exp_acc is not None

    # 1. Post a complex multi-line journal entry
    multi_lines = [
        {
            "account_id": bank_acc.id,
            "debit_amount": Decimal("10000.0000"),
            "credit_amount": Decimal("0.0000"),
        },
        {"account_id": exp_acc.id, "debit_amount": Decimal("2500.0000"), "credit_amount": Decimal("0.0000")},
        {
            "account_id": income_acc.id,
            "debit_amount": Decimal("0.0000"),
            "credit_amount": Decimal("12500.0000"),
        },
    ]
    jv1 = await journal_service.create_draft_journal(
        society_id=SOCIETY_A_ID,
        financial_period_id=period.id,
        entry_date=date(2026, 6, 1),
        description="Multi-leg complex transaction",
        lines_data=multi_lines,
        created_by=USER_ADMIN_ID,
    )
    await journal_service.post_journal(SOCIETY_A_ID, jv1.id, posted_by=USER_ADMIN_ID)

    # 2. Create, approve, and post an operational expense
    exp = await expense_service.create_expense(
        society_id=SOCIETY_A_ID,
        financial_period_id=period.id,
        expense_date=date(2026, 6, 5),
        category_account_id=exp_acc.id,
        paid_from_account_id=bank_acc.id,
        description="Lift AMC quarterly service",
        amount=Decimal("4500.0000"),
        created_by=USER_ADMIN_ID,
    )
    await expense_service.approve_expense(exp.id, SOCIETY_A_ID, approved_by=USER_ADMIN_ID)
    await expense_service.post_expense(exp.id, SOCIETY_A_ID, posted_by=USER_ADMIN_ID)

    # 3. Post another entry and reverse it
    jv2 = await journal_service.create_draft_journal(
        society_id=SOCIETY_A_ID,
        financial_period_id=period.id,
        entry_date=date(2026, 6, 10),
        description="Temporary Entry to Reverse",
        lines_data=[
            {
                "account_id": bank_acc.id,
                "debit_amount": Decimal("1000.0000"),
                "credit_amount": Decimal("0.0000"),
            },
            {
                "account_id": income_acc.id,
                "debit_amount": Decimal("0.0000"),
                "credit_amount": Decimal("1000.0000"),
            },
        ],
        created_by=USER_ADMIN_ID,
    )
    await journal_service.post_journal(SOCIETY_A_ID, jv2.id, posted_by=USER_ADMIN_ID)
    await journal_service.reverse_journal(
        SOCIETY_A_ID, jv2.id, reason="Correction", reversed_by=USER_ADMIN_ID
    )

    # 4. Verify Society-wide double-entry invariant across all posted journal lines
    stmt = (
        select(
            func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label("society_total_debits"),
            func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label("society_total_credits"),
        )
        .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
        .where(
            JournalEntryLine.society_id == SOCIETY_A_ID,
            JournalEntry.society_id == SOCIETY_A_ID,
            JournalEntry.status == "POSTED",
        )
    )

    res = await seeded_session.execute(stmt)
    total_debits, total_credits = res.one()

    total_debits = quantize_amount(Decimal(str(total_debits)))
    total_credits = quantize_amount(Decimal(str(total_credits)))

    assert total_debits > Decimal("0.0000")
    assert total_credits > Decimal("0.0000")
    assert total_debits == total_credits
    assert (total_debits - total_credits) == Decimal("0.0000")
