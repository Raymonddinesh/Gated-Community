"""Tests for Payment Recording, Explicit Allocation, FIFO Allocation, and Receipts."""

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.billing.application.payment_service import PaymentService
from apps.api.src.billing.domain.exceptions import (
    PaymentOverAllocationException,
)
from apps.api.src.billing.infrastructure.repositories import InvoiceRepository
from apps.api.src.core.exceptions import AppException

SOCIETY_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SOCIETY_B_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
USER_OWNER_A = UUID("22222222-2222-2222-2222-22222222222a")
USER_TENANT_A = UUID("33333333-3333-3333-3333-33333333333a")


@pytest.mark.asyncio
async def test_record_payment_and_receipt_issuance(seeded_session: AsyncSession) -> None:
    """Recording payment generates a sequential receipt and posts accounting entry."""
    payment_service = PaymentService(seeded_session)

    payment = await payment_service.record_payment(
        society_id=SOCIETY_A_ID,
        payer_user_id=USER_OWNER_A,
        amount=Decimal("1500.0000"),
        payment_date=date(2026, 4, 10),
        reference_number="NEFT-20260410-099",
        payment_method="BANK_TRANSFER",
        created_by=USER_OWNER_A,
        auto_allocate=False,
    )

    assert payment.id is not None
    assert payment.amount == Decimal("1500.0000")
    assert payment.unallocated_amount == Decimal("1500.0000")
    assert payment.status == "RECORDED"

    # Verify receipt issued
    receipts = await payment_service.list_receipts(SOCIETY_A_ID, payer_user_id=USER_OWNER_A)
    ref_receipts = [r for r in receipts if r.payment_id == payment.id]
    assert len(ref_receipts) == 1
    assert ref_receipts[0].amount == Decimal("1500.0000")
    assert ref_receipts[0].receipt_number.startswith("REC-")


@pytest.mark.asyncio
async def test_explicit_allocation_and_over_allocation_guard(seeded_session: AsyncSession) -> None:
    """Explicit allocation against an invoice updates balances and prevents over-allocation."""
    payment_service = PaymentService(seeded_session)
    invoice_repo = InvoiceRepository(seeded_session)

    inv = await invoice_repo.get_by_number("INV-000002", SOCIETY_A_ID)
    assert inv is not None
    assert inv.outstanding_amount > Decimal("0.0000")

    payment = await payment_service.record_payment(
        society_id=SOCIETY_A_ID,
        payer_user_id=USER_TENANT_A,
        amount=Decimal("1000.0000"),
        payment_date=date(2026, 4, 12),
        reference_number="UPI-20260412-888",
        created_by=USER_TENANT_A,
        auto_allocate=False,
    )

    initial_outstanding = inv.outstanding_amount

    # 1. Allocate valid amount (500.00)
    await payment_service.allocate_payment(
        society_id=SOCIETY_A_ID,
        payment_id=payment.id,
        invoice_id=inv.id,
        amount=Decimal("500.0000"),
        allocated_by=USER_TENANT_A,
    )

    assert payment.allocated_amount == Decimal("500.0000")
    assert payment.unallocated_amount == Decimal("500.0000")
    assert inv.paid_amount == Decimal("500.0000")
    assert inv.outstanding_amount == initial_outstanding - Decimal("500.0000")
    assert inv.status == "PARTIALLY_PAID"

    # 2. Over-allocation exceeding payment unallocated balance is rejected
    with pytest.raises(PaymentOverAllocationException):
        await payment_service.allocate_payment(
            society_id=SOCIETY_A_ID,
            payment_id=payment.id,
            invoice_id=inv.id,
            amount=Decimal("9999.0000"),
            allocated_by=USER_TENANT_A,
        )


@pytest.mark.asyncio
async def test_cross_tenant_allocation_blocked(seeded_session: AsyncSession) -> None:
    """Allocating a payment from Society A to an invoice in Society B must be strictly blocked."""
    payment_service = PaymentService(seeded_session)
    invoice_repo = InvoiceRepository(seeded_session)

    # Society A payment
    payment = await payment_service.record_payment(
        society_id=SOCIETY_A_ID,
        payer_user_id=USER_OWNER_A,
        amount=Decimal("500.0000"),
        payment_date=date(2026, 4, 12),
        reference_number="UPI-TEST-001",
        auto_allocate=False,
    )

    # Invoices for Society B
    invs_b = await invoice_repo.list_invoices(SOCIETY_B_ID)
    if invs_b:
        with pytest.raises(AppException):
            await payment_service.allocate_payment(
                society_id=SOCIETY_A_ID,
                payment_id=payment.id,
                invoice_id=invs_b[0].id,
                amount=Decimal("500.0000"),
            )


@pytest.mark.asyncio
async def test_cancelled_or_draft_invoice_allocation_blocked(seeded_session: AsyncSession) -> None:
    """Cancelled or draft invoices must be rejected from receiving payment allocations."""
    payment_service = PaymentService(seeded_session)
    invoice_repo = InvoiceRepository(seeded_session)

    inv = await invoice_repo.get_by_number("INV-000002", SOCIETY_A_ID)
    assert inv is not None

    payment = await payment_service.record_payment(
        society_id=SOCIETY_A_ID,
        payer_user_id=USER_TENANT_A,
        amount=Decimal("500.0000"),
        payment_date=date(2026, 4, 15),
        reference_number="UPI-TEST-002",
        auto_allocate=False,
    )

    # Temporarily mark invoice as CANCELLED
    inv.status = "CANCELLED"
    await seeded_session.flush()

    with pytest.raises(AppException) as exc_info:
        await payment_service.allocate_payment(
            society_id=SOCIETY_A_ID,
            payment_id=payment.id,
            invoice_id=inv.id,
            amount=Decimal("200.0000"),
            allocated_by=USER_TENANT_A,
        )
    assert exc_info.value.code == "INVOICE_NOT_PAYABLE"


@pytest.mark.asyncio
async def test_payment_idempotency_and_duplicate_prevention(seeded_session: AsyncSession) -> None:
    """Submitting payment with identical idempotency key returns existing payment without duplicating records."""
    payment_service = PaymentService(seeded_session)

    idemp_key = "IDEMP-TEST-KEY-001"
    pay1 = await payment_service.record_payment(
        society_id=SOCIETY_A_ID,
        payer_user_id=USER_OWNER_A,
        amount=Decimal("2000.0000"),
        payment_date=date(2026, 4, 18),
        reference_number="REF-IDEMP-001",
        idempotency_key=idemp_key,
        auto_allocate=False,
    )

    pay2 = await payment_service.record_payment(
        society_id=SOCIETY_A_ID,
        payer_user_id=USER_OWNER_A,
        amount=Decimal("2000.0000"),
        payment_date=date(2026, 4, 18),
        reference_number="REF-IDEMP-001",
        idempotency_key=idemp_key,
        auto_allocate=False,
    )

    assert pay1.id == pay2.id


@pytest.mark.asyncio
async def test_payment_reversal_unwinds_allocations_and_voids_receipt(seeded_session: AsyncSession) -> None:
    """Reversing a payment unwinds applied invoice allocations, cancels receipts, and posts reversal journal."""
    payment_service = PaymentService(seeded_session)
    invoice_repo = InvoiceRepository(seeded_session)

    inv = await invoice_repo.get_by_number("INV-000002", SOCIETY_A_ID)
    assert inv is not None
    initial_outstanding = inv.outstanding_amount

    # Record and allocate ₹800
    payment = await payment_service.record_payment(
        society_id=SOCIETY_A_ID,
        payer_user_id=USER_TENANT_A,
        amount=Decimal("800.0000"),
        payment_date=date(2026, 4, 20),
        reference_number="PAY-REV-001",
        auto_allocate=False,
    )
    await payment_service.allocate_payment(
        society_id=SOCIETY_A_ID,
        payment_id=payment.id,
        invoice_id=inv.id,
        amount=Decimal("800.0000"),
    )

    assert inv.outstanding_amount == initial_outstanding - Decimal("800.0000")

    # Reverse payment
    reversed_pay = await payment_service.reverse_payment(
        society_id=SOCIETY_A_ID,
        payment_id=payment.id,
        reason="Cheque dishonoured by issuing bank",
    )

    assert reversed_pay.status == "REVERSED"
    assert reversed_pay.reversal_journal_entry_id is not None
    assert reversed_pay.allocated_amount == Decimal("0.0000")
    # Invoice outstanding restored
    assert inv.outstanding_amount == initial_outstanding

    # Receipt marked cancelled
    assert payment.receipt is not None
    receipt = await payment_service.get_receipt(payment.receipt.id, SOCIETY_A_ID)
    assert receipt.status == "CANCELLED"


@pytest.mark.asyncio
async def test_bank_reconciliation_workflow_and_matching(seeded_session: AsyncSession) -> None:
    """Reconciliation session matches recorded payments, detects discrepancies, and closes properly."""
    from apps.api.src.billing.application.integrity_service import IntegrityReconciliationService
    from apps.api.src.billing.application.reconciliation_service import ReconciliationService
    from apps.api.src.finance.infrastructure.repositories import AccountRepository

    recon_service = ReconciliationService(seeded_session)
    account_repo = AccountRepository(seeded_session)
    accounts = await account_repo.list_accounts(SOCIETY_A_ID)
    bank_acc = next(a for a in accounts if a.account_code == "1010")

    # 1. Create reconciliation session
    sess = await recon_service.create_session(
        society_id=SOCIETY_A_ID,
        account_id=bank_acc.id,
        statement_reference="STMT-TEST-202604",
        statement_start_date=date(2026, 4, 1),
        statement_end_date=date(2026, 4, 30),
        opening_balance=Decimal("50000.0000"),
        closing_balance=Decimal("55000.0000"),
    )
    assert sess.session_number.startswith("REC-SESS-")
    assert sess.status == "OPEN"

    # 2. Add item matching existing seed payment
    payment_service = PaymentService(seeded_session)
    payments = await payment_service.list_payments(SOCIETY_A_ID)
    seed_payment = payments[0]

    item = await recon_service.add_statement_item(
        society_id=SOCIETY_A_ID,
        session_id=sess.id,
        transaction_date=date(2026, 4, 5),
        reference_number=seed_payment.reference_number,
        description="Bank deposit matching seed payment",
        statement_amount=seed_payment.amount,
        payment_id=seed_payment.id,
    )
    assert item.match_status == "MATCHED"
    assert item.discrepancy_amount == Decimal("0.0000")

    # 3. Close session
    closed_sess = await recon_service.close_session(SOCIETY_A_ID, sess.id)
    assert closed_sess.status == "CLOSED"

    # 4. Run integrity audit
    integrity_service = IntegrityReconciliationService(seeded_session)
    integrity_report = await integrity_service.verify_society_billing_integrity(SOCIETY_A_ID)
    assert integrity_report["is_healthy"] is True
    assert integrity_report["issue_count"] == 0
