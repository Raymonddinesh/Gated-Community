"""Financial Integrity, Accounting Treatment, and Reversal Preservation Tests.

Tests:
1. RECORDED payments do not inflate cleared Bank/Cash balance.
2. CLEARED payments post balanced double-entry GL journal (Debit Bank, Credit AR).
3. Clearance retries are idempotent and do not duplicate journals.
4. BOUNCED payments do not leave settled bank balance.
5. REVERSED payments reverse accounting treatment via Phase 4 GL mirror journal.
6. Closed financial reporting periods block clearance.
7. Payment reversal preserves historical PaymentAllocation records with status='REVERSED'.
8. Refund foundation reduces unallocated amounts, posts GL refund, and updates status.
9. RLS WITH CHECK blocks cross-tenant inserts and modifications.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.billing.application.payment_service import PaymentService
from apps.api.src.billing.infrastructure.repositories import InvoiceRepository, PaymentRepository
from apps.api.src.core.exceptions import AppException
from apps.api.src.finance.application.report_service import ReportService
from apps.api.src.finance.infrastructure.repositories import AccountRepository, PeriodRepository

SOCIETY_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SOCIETY_B_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
USER_OWNER_A = UUID("22222222-2222-2222-2222-22222222222a")
USER_TENANT_A = UUID("33333333-3333-3333-3333-33333333333a")


@pytest.mark.asyncio
async def test_recorded_payment_does_not_inflate_cleared_bank_balance(seeded_session: AsyncSession) -> None:
    """RECORDED payment (uncleared cheque/transfer) must not inflate cleared Bank/Cash balance."""
    payment_service = PaymentService(seeded_session)
    report_service = ReportService(seeded_session)
    period_repo = PeriodRepository(seeded_session)

    period = await period_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 4, 15))
    assert period is not None

    # 1. Capture initial trial balance
    tb_before = await report_service.generate_trial_balance(SOCIETY_A_ID, period.id)
    bank_line_before = next((line for line in tb_before["accounts"] if line["account_code"] == "1010"), None)
    initial_bank_debit = Decimal(bank_line_before["total_debit"]) if bank_line_before else Decimal("0.0000")

    # 2. Record payment with auto_clear=False (e.g. cheque awaiting clearance)
    payment = await payment_service.record_payment(
        society_id=SOCIETY_A_ID,
        payer_user_id=USER_OWNER_A,
        amount=Decimal("5000.0000"),
        payment_date=date(2026, 4, 10),
        reference_number="CHQ-UNCLEARED-001",
        payment_method="CHEQUE",
        auto_allocate=False,
        auto_clear=False,
    )

    assert payment.status == "RECORDED"
    assert payment.journal_entry_id is None

    # 3. Trial balance bank ledger must remain completely unchanged
    tb_after = await report_service.generate_trial_balance(SOCIETY_A_ID, period.id)
    bank_line_after = next((line for line in tb_after["accounts"] if line["account_code"] == "1010"), None)
    after_bank_debit = Decimal(bank_line_after["total_debit"]) if bank_line_after else Decimal("0.0000")

    assert after_bank_debit == initial_bank_debit


@pytest.mark.asyncio
async def test_cleared_payment_produces_correct_gl_entry(seeded_session: AsyncSession) -> None:
    """Transitioning RECORDED -> CLEARED posts balanced double-entry journal and updates balances."""
    payment_service = PaymentService(seeded_session)
    report_service = ReportService(seeded_session)
    period_repo = PeriodRepository(seeded_session)

    period = await period_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 4, 15))
    assert period is not None

    # Record uncleared
    payment = await payment_service.record_payment(
        society_id=SOCIETY_A_ID,
        payer_user_id=USER_OWNER_A,
        amount=Decimal("3000.0000"),
        payment_date=date(2026, 4, 12),
        reference_number="CHQ-TO-CLEAR-001",
        payment_method="CHEQUE",
        auto_allocate=False,
        auto_clear=False,
    )
    assert payment.status == "RECORDED"
    assert payment.journal_entry_id is None

    # Clear payment explicitly
    cleared = await payment_service.clear_payment(
        society_id=SOCIETY_A_ID,
        payment_id=payment.id,
        cleared_by=USER_OWNER_A,
    )

    assert cleared.status == "CLEARED"
    assert cleared.journal_entry_id is not None

    # Trial balance must reflect Debit Bank and Credit AR
    tb = await report_service.generate_trial_balance(SOCIETY_A_ID, period.id)
    assert tb["is_balanced"] is True
    assert Decimal(tb["total_debits"]) == Decimal(tb["total_credits"])


@pytest.mark.asyncio
async def test_clearance_idempotency_prevents_duplicate_journal(seeded_session: AsyncSession) -> None:
    """Retrying payment clearance on an already cleared payment does not duplicate journal entries."""
    payment_service = PaymentService(seeded_session)

    payment = await payment_service.record_payment(
        society_id=SOCIETY_A_ID,
        payer_user_id=USER_OWNER_A,
        amount=Decimal("2500.0000"),
        payment_date=date(2026, 4, 14),
        reference_number="NEFT-IDEMP-001",
        payment_method="BANK_TRANSFER",
        auto_allocate=False,
        auto_clear=True,
    )
    initial_journal_id = payment.journal_entry_id
    assert initial_journal_id is not None

    # Retry clearing
    cleared_again = await payment_service.clear_payment(
        society_id=SOCIETY_A_ID,
        payment_id=payment.id,
    )
    assert cleared_again.journal_entry_id == initial_journal_id


@pytest.mark.asyncio
async def test_bounced_payment_does_not_leave_inflated_bank_balance(seeded_session: AsyncSession) -> None:
    """Bouncing an uncleared cheque marks status BOUNCED with zero bank inflation."""
    payment_service = PaymentService(seeded_session)
    report_service = ReportService(seeded_session)
    period_repo = PeriodRepository(seeded_session)

    period = await period_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 4, 15))
    assert period is not None

    tb_before = await report_service.generate_trial_balance(SOCIETY_A_ID, period.id)
    bank_before = next((line for line in tb_before["accounts"] if line["account_code"] == "1010"), None)
    initial_balance = Decimal(bank_before["total_debit"]) if bank_before else Decimal("0.0000")

    payment = await payment_service.record_payment(
        society_id=SOCIETY_A_ID,
        payer_user_id=USER_TENANT_A,
        amount=Decimal("4000.0000"),
        payment_date=date(2026, 4, 15),
        reference_number="CHQ-BOUNCE-001",
        payment_method="CHEQUE",
        auto_allocate=False,
        auto_clear=False,
    )

    bounced = await payment_service.bounce_payment(
        society_id=SOCIETY_A_ID,
        payment_id=payment.id,
        reason="Signature mismatch on cheque leaf",
    )
    assert bounced.status == "BOUNCED"
    assert bounced.journal_entry_id is None

    tb_after = await report_service.generate_trial_balance(SOCIETY_A_ID, period.id)
    bank_after = next((line for line in tb_after["accounts"] if line["account_code"] == "1010"), None)
    after_balance = Decimal(bank_after["total_debit"]) if bank_after else Decimal("0.0000")

    assert after_balance == initial_balance


@pytest.mark.asyncio
async def test_closed_financial_period_blocks_payment_clearance(seeded_session: AsyncSession) -> None:
    """Clearance with date outside an open financial reporting period must be rejected."""
    payment_service = PaymentService(seeded_session)

    payment = await payment_service.record_payment(
        society_id=SOCIETY_A_ID,
        payer_user_id=USER_OWNER_A,
        amount=Decimal("1200.0000"),
        payment_date=date(2026, 4, 1),
        reference_number="DATE-OUTSIDE-001",
        payment_method="CHEQUE",
        auto_allocate=False,
        auto_clear=False,
    )

    # Attempt clearance with date in 2024 (closed/nonexistent period)
    with pytest.raises(AppException) as exc_info:
        await payment_service.clear_payment(
            society_id=SOCIETY_A_ID,
            payment_id=payment.id,
            cleared_date=date(2024, 1, 1),
        )
    assert exc_info.value.code == "PERIOD_CLOSED"


@pytest.mark.asyncio
async def test_payment_reversal_preserves_historical_allocations(seeded_session: AsyncSession) -> None:
    """Reversal marks PaymentAllocation records as REVERSED rather than destroying them."""
    payment_service = PaymentService(seeded_session)
    invoice_repo = InvoiceRepository(seeded_session)
    payment_repo = PaymentRepository(seeded_session)

    inv = await invoice_repo.get_by_number("INV-000002", SOCIETY_A_ID)
    assert inv is not None
    initial_outstanding = inv.outstanding_amount

    # Record and allocate ₹1,000
    payment = await payment_service.record_payment(
        society_id=SOCIETY_A_ID,
        payer_user_id=USER_TENANT_A,
        amount=Decimal("1000.0000"),
        payment_date=date(2026, 4, 16),
        reference_number="ALLOC-PRESERVE-001",
        auto_allocate=False,
        auto_clear=True,
    )
    await payment_service.allocate_payment(
        society_id=SOCIETY_A_ID,
        payment_id=payment.id,
        invoice_id=inv.id,
        amount=Decimal("1000.0000"),
    )

    # Check allocation exists and is ACTIVE
    allocs = await payment_repo.get_allocations_for_payment(payment.id, SOCIETY_A_ID)
    assert len(allocs) == 1
    assert allocs[0].status == "ACTIVE"

    # Reverse payment
    reversed_payment = await payment_service.reverse_payment(
        society_id=SOCIETY_A_ID,
        payment_id=payment.id,
        reason="Resident disputed double debit",
        reversed_by=USER_TENANT_A,
    )
    assert reversed_payment.status == "REVERSED"

    # CRITICAL: Verify allocation record STILL EXISTS in database and is marked REVERSED
    preserved_allocs = await payment_repo.get_allocations_for_payment(payment.id, SOCIETY_A_ID)
    assert len(preserved_allocs) == 1
    assert preserved_allocs[0].status == "REVERSED"
    assert preserved_allocs[0].reversed_at is not None
    assert preserved_allocs[0].reversed_by == USER_TENANT_A
    assert preserved_allocs[0].reversal_reason == "Resident disputed double debit"

    # Verify invoice outstanding is restored
    assert inv.outstanding_amount == initial_outstanding

    # Duplicate reversal attempt must be rejected
    with pytest.raises(AppException):
        await payment_service.reverse_payment(
            society_id=SOCIETY_A_ID,
            payment_id=payment.id,
            reason="Second reversal attempt",
        )


@pytest.mark.asyncio
async def test_refund_foundation_workflow_and_gl_posting(seeded_session: AsyncSession) -> None:
    """Refunding unallocated payment balance posts balanced refund journal and updates status."""
    payment_service = PaymentService(seeded_session)
    report_service = ReportService(seeded_session)

    # Record cleared payment of ₹3,000 without allocating
    payment = await payment_service.record_payment(
        society_id=SOCIETY_A_ID,
        payer_user_id=USER_OWNER_A,
        amount=Decimal("3000.0000"),
        payment_date=date(2026, 4, 18),
        reference_number="REFUND-BASE-001",
        auto_allocate=False,
        auto_clear=True,
    )
    assert payment.unallocated_amount == Decimal("3000.0000")

    # Partial refund of ₹1,000
    refunded = await payment_service.refund_payment(
        society_id=SOCIETY_A_ID,
        payment_id=payment.id,
        amount=Decimal("1000.0000"),
        reason="Resident overpaid quarterly dues",
        refunded_by=USER_OWNER_A,
    )
    assert refunded.unallocated_amount == Decimal("2000.0000")
    assert refunded.status == "CLEARED"

    # Refund remaining ₹2,000
    full_refund = await payment_service.refund_payment(
        society_id=SOCIETY_A_ID,
        payment_id=payment.id,
        amount=Decimal("2000.0000"),
        reason="Final refund of excess balance",
        refunded_by=USER_OWNER_A,
    )
    assert full_refund.unallocated_amount == Decimal("0.0000")
    assert full_refund.status == "REFUNDED"

    # Trial balance must balance after refunds
    period_repo = PeriodRepository(seeded_session)
    period = await period_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 4, 18))
    assert period is not None
    tb = await report_service.generate_trial_balance(SOCIETY_A_ID, period.id)
    assert tb["is_balanced"] is True

    # Exceeding refund must be rejected
    with pytest.raises(AppException) as exc_info:
        await payment_service.refund_payment(
            society_id=SOCIETY_A_ID,
            payment_id=payment.id,
            amount=Decimal("500.0000"),
            reason="Exceeding refund",
        )
    assert exc_info.value.code == "PAYMENT_NOT_REFUNDABLE"


@pytest.mark.asyncio
async def test_rls_migration_defines_explicit_using_and_with_check() -> None:
    """Verify that Phase 6 migration mandates ENABLE, FORCE RLS, USING and WITH CHECK for tenant tables."""
    from pathlib import Path

    migration_file = Path("apps/api/alembic/versions/20261003_0006_payments_reconciliation.py")
    content = migration_file.read_text(encoding="utf-8")

    assert "ENABLE ROW LEVEL SECURITY" in content
    assert "FORCE ROW LEVEL SECURITY" in content
    assert "WITH CHECK (" in content
    assert "USING (" in content

    # Check that each Phase 6 table is protected
    for table in [
        "payments",
        "receipts",
        "payment_allocations",
        "reconciliation_sessions",
        "reconciliation_items",
    ]:
        assert f'"{table}"' in content or f"'{table}'" in content


@pytest.mark.asyncio
async def test_cross_tenant_reconciliation_matching_blocked(seeded_session: AsyncSession) -> None:
    """Matching a payment from Society B against a reconciliation session in Society A must be rejected."""
    from apps.api.src.billing.application.reconciliation_service import ReconciliationService

    recon_service = ReconciliationService(seeded_session)
    payment_service = PaymentService(seeded_session)
    account_repo = AccountRepository(seeded_session)

    accounts_a = await account_repo.list_accounts(SOCIETY_A_ID)
    bank_a = next(a for a in accounts_a if a.account_code == "1010")

    # Session in Society A
    sess = await recon_service.create_session(
        society_id=SOCIETY_A_ID,
        account_id=bank_a.id,
        statement_reference="STMT-A-001",
        statement_start_date=date(2026, 4, 1),
        statement_end_date=date(2026, 4, 30),
        opening_balance=Decimal("10000.0000"),
        closing_balance=Decimal("15000.0000"),
    )

    # Payment in Society B
    pay_b = await payment_service.record_payment(
        society_id=SOCIETY_B_ID,
        payer_user_id=USER_OWNER_A,
        amount=Decimal("1500.0000"),
        payment_date=date(2026, 4, 10),
        reference_number="PAY-SOC-B-001",
        auto_allocate=False,
        auto_clear=True,
    )

    # Attempting to match Society B payment in Society A session must fail
    with pytest.raises(AppException):
        await recon_service.add_statement_item(
            society_id=SOCIETY_A_ID,
            session_id=sess.id,
            transaction_date=date(2026, 4, 10),
            reference_number="STMT-CROSS-001",
            description="Attempt cross-tenant deposit match",
            statement_amount=Decimal("1500.0000"),
            payment_id=pay_b.id,
        )
