"""Tests for Deterministic Financial Statements and Reporting Engine."""

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.finance.application.journal_service import JournalService
from apps.api.src.finance.application.report_service import ReportService
from apps.api.src.finance.infrastructure.repositories import (
    AccountRepository,
    PeriodRepository,
)

SOCIETY_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER_ADMIN_ID = UUID("22222222-2222-2222-2222-22222222222a")


@pytest.mark.asyncio
async def test_trial_balance_is_balanced(seeded_session: AsyncSession) -> None:
    """Trial Balance must be strictly balanced: total debits == total credits."""
    report_service = ReportService(seeded_session)
    period_repo = PeriodRepository(seeded_session)

    period = await period_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 4, 15))
    assert period is not None

    tb = await report_service.generate_trial_balance(SOCIETY_A_ID, period.id)

    assert tb["is_balanced"] is True
    assert Decimal(tb["total_debits"]) == Decimal(tb["total_credits"])
    assert Decimal(tb["total_debits"]) == Decimal("50000.0000")


@pytest.mark.asyncio
async def test_draft_journals_excluded_from_trial_balance(seeded_session: AsyncSession) -> None:
    """Draft journal entries must not affect the Trial Balance or general ledger."""
    report_service = ReportService(seeded_session)
    journal_service = JournalService(seeded_session)
    period_repo = PeriodRepository(seeded_session)
    account_repo = AccountRepository(seeded_session)

    period = await period_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 4, 15))
    bank_acc = await account_repo.get_by_code(SOCIETY_A_ID, "1010")
    income_acc = await account_repo.get_by_code(SOCIETY_A_ID, "4000")
    assert period is not None and bank_acc is not None and income_acc is not None

    # Get initial TB total
    tb_before = await report_service.generate_trial_balance(SOCIETY_A_ID, period.id)
    initial_total = Decimal(tb_before["total_debits"])

    # Create a draft journal (NOT posted)
    lines = [
        {
            "account_id": bank_acc.id,
            "debit_amount": Decimal("25000.0000"),
            "credit_amount": Decimal("0.0000"),
        },
        {
            "account_id": income_acc.id,
            "debit_amount": Decimal("0.0000"),
            "credit_amount": Decimal("25000.0000"),
        },
    ]
    await journal_service.create_draft_journal(
        society_id=SOCIETY_A_ID,
        financial_period_id=period.id,
        entry_date=date(2026, 4, 20),
        description="Draft Entry to ignore",
        lines_data=lines,
    )

    # TB total must remain unchanged
    tb_after = await report_service.generate_trial_balance(SOCIETY_A_ID, period.id)
    assert Decimal(tb_after["total_debits"]) == initial_total
    assert tb_after["is_balanced"] is True


@pytest.mark.asyncio
async def test_income_expenditure_and_balance_sheet(seeded_session: AsyncSession) -> None:
    """Verify Income & Expenditure Statement and Balance Sheet calculation logic."""
    report_service = ReportService(seeded_session)
    journal_service = JournalService(seeded_session)
    period_repo = PeriodRepository(seeded_session)
    account_repo = AccountRepository(seeded_session)

    period = await period_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 5, 10))
    bank_acc = await account_repo.get_by_code(SOCIETY_A_ID, "1010")
    sec_exp_acc = await account_repo.get_by_code(SOCIETY_A_ID, "5000")
    assert period is not None and bank_acc is not None and sec_exp_acc is not None

    # Post an expense entry: Debit 5000 (Security Services) 15000, Credit 1010 (Bank) 15000
    expense_lines = [
        {
            "account_id": sec_exp_acc.id,
            "debit_amount": Decimal("15000.0000"),
            "credit_amount": Decimal("0.0000"),
        },
        {
            "account_id": bank_acc.id,
            "debit_amount": Decimal("0.0000"),
            "credit_amount": Decimal("15000.0000"),
        },
    ]
    exp_journal = await journal_service.create_draft_journal(
        society_id=SOCIETY_A_ID,
        financial_period_id=period.id,
        entry_date=date(2026, 5, 10),
        description="Security Agency Monthly Bill",
        lines_data=expense_lines,
    )
    await journal_service.post_journal(SOCIETY_A_ID, exp_journal.id, posted_by=USER_ADMIN_ID)

    # 1. Test Income & Expenditure
    # Seeded income: 50,000; Posted expense: 15,000; Net surplus: 35,000
    ie = await report_service.generate_income_and_expenditure(SOCIETY_A_ID, period.id)
    assert Decimal(ie["total_income"]) == Decimal("50000.0000")
    assert Decimal(ie["total_expenditure"]) == Decimal("15000.0000")
    assert Decimal(ie["net_surplus"]) == Decimal("35000.0000")

    # 2. Test Balance Sheet
    # Assets: Bank = 50,000 - 15,000 = 35,000
    # Liabilities: 0
    # Equity: 0 + current year surplus 35,000 = 35,000
    # Total Assets (35,000) == Total Liab + Equity (35,000)
    bs = await report_service.generate_balance_sheet(SOCIETY_A_ID, period.id)
    assert bs["is_balanced"] is True
    assert Decimal(bs["total_assets"]) == Decimal("35000.0000")
    assert Decimal(bs["total_liabilities_and_equity"]) == Decimal("35000.0000")


@pytest.mark.asyncio
async def test_general_ledger_running_balance(seeded_session: AsyncSession) -> None:
    """General Ledger tracks chronological entries and produces correct running closing balance."""
    report_service = ReportService(seeded_session)
    period_repo = PeriodRepository(seeded_session)
    account_repo = AccountRepository(seeded_session)

    period = await period_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 4, 15))
    bank_acc = await account_repo.get_by_code(SOCIETY_A_ID, "1010")
    assert period is not None and bank_acc is not None

    gl = await report_service.generate_general_ledger(
        society_id=SOCIETY_A_ID,
        account_id=bank_acc.id,
        financial_period_id=period.id,
    )

    assert gl["account_code"] == "1010"
    assert len(gl["entries"]) >= 1
    assert Decimal(gl["closing_balance"]) >= Decimal("0.0000")
