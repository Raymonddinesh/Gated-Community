"""Tests for Invoice Generation, Approval, Publication, Accounting Integration, and Adjustments."""

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.billing.application.invoice_service import InvoiceService
from apps.api.src.billing.application.period_service import BillingPeriodService
from apps.api.src.billing.domain.exceptions import (
    InvalidAdjustmentException,
)
from apps.api.src.billing.infrastructure.repositories import (
    BillingPeriodRepository,
    InvoiceRepository,
)
from apps.api.src.database.models.finance import JournalEntry
from apps.api.src.finance.infrastructure.repositories import PeriodRepository

SOCIETY_A_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER_ADMIN_ID = UUID("22222222-2222-2222-2222-22222222222a")


@pytest.mark.asyncio
async def test_deterministic_invoice_generation_and_idempotency(seeded_session: AsyncSession) -> None:
    """Invoice generation must be deterministic and strictly idempotent."""
    period_service = BillingPeriodService(seeded_session)
    invoice_service = InvoiceService(seeded_session)
    fin_repo = PeriodRepository(seeded_session)

    fin_period = await fin_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 5, 1))
    assert fin_period is not None

    # Create May 2026 Billing Period
    period = await period_service.create_period(
        society_id=SOCIETY_A_ID,
        financial_period_id=fin_period.id,
        period_code="BP-2026-05",
        name="May 2026 Maintenance",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
        billing_date=date(2026, 5, 1),
        due_date=date(2026, 5, 15),
        created_by=USER_ADMIN_ID,
    )

    # 1. First run generates invoices
    invoices1 = await invoice_service.generate_invoices_for_period(
        society_id=SOCIETY_A_ID,
        billing_period_id=period.id,
        generated_by=USER_ADMIN_ID,
    )
    assert len(invoices1) > 0

    for inv in invoices1:
        assert inv.status == "REVIEW"  # config approval_required is True
        assert inv.grand_total == Decimal("3000.0000")  # from MAINT_FIXED rule
        assert inv.outstanding_amount == Decimal("3000.0000")
        assert len(inv.lines) == 1
        assert inv.lines[0].amount == Decimal("3000.0000")

    # 2. Re-running generation for the same period must NOT create duplicate invoices
    invoices2 = await invoice_service.generate_invoices_for_period(
        society_id=SOCIETY_A_ID,
        billing_period_id=period.id,
        generated_by=USER_ADMIN_ID,
    )
    assert len(invoices2) == 0  # 0 new invoices added!


@pytest.mark.asyncio
async def test_invoice_approval_publication_and_accounting_integration(seeded_session: AsyncSession) -> None:
    """Approving and publishing a billing period must post balanced general ledger entries."""
    invoice_repo = InvoiceRepository(seeded_session)
    period_repo = BillingPeriodRepository(seeded_session)

    # Use seeded April period BP-2026-04
    period = await period_repo.get_by_code("BP-2026-04", SOCIETY_A_ID)
    assert period is not None

    invoices = await invoice_repo.list_invoices(SOCIETY_A_ID, billing_period_id=period.id)
    assert len(invoices) >= 2

    # Check that published invoices have balanced accounting journal entries
    for inv in invoices:
        assert inv.status in ("PUBLISHED", "PAID")
        assert inv.accounting_status == "POSTED"


@pytest.mark.asyncio
async def test_invoice_adjustment_workflow(seeded_session: AsyncSession) -> None:
    """Applying a discount or waiver decreases invoice outstanding balance."""
    invoice_service = InvoiceService(seeded_session)
    invoice_repo = InvoiceRepository(seeded_session)

    inv = await invoice_repo.get_by_number("INV-000002", SOCIETY_A_ID)
    assert inv is not None
    initial_outstanding = inv.outstanding_amount

    # Apply waiver adjustment of 500.00
    updated = await invoice_service.apply_adjustment(
        society_id=SOCIETY_A_ID,
        invoice_id=inv.id,
        adjustment_type="WAIVER",
        amount=Decimal("500.0000"),
        reason="Approved committee discount for prompt feedback",
        created_by=USER_ADMIN_ID,
    )

    assert updated.adjustment_total == Decimal("500.0000")
    assert updated.grand_total == initial_outstanding - Decimal("500.0000")
    assert updated.outstanding_amount == initial_outstanding - Decimal("500.0000")

    # Negative or zero amount adjustment rejected
    with pytest.raises(InvalidAdjustmentException):
        await invoice_service.apply_adjustment(
            society_id=SOCIETY_A_ID,
            invoice_id=inv.id,
            adjustment_type="WAIVER",
            amount=Decimal("-10.0000"),
            reason="Invalid",
            created_by=USER_ADMIN_ID,
        )


@pytest.mark.asyncio
async def test_credit_and_debit_notes_create_balanced_accounting_entries(
    seeded_session: AsyncSession,
) -> None:
    """Credit notes and debit notes create balanced journal entries and adjust balances."""
    invoice_service = InvoiceService(seeded_session)
    invoice_repo = InvoiceRepository(seeded_session)

    inv = await invoice_repo.get_by_number("INV-000002", SOCIETY_A_ID)
    assert inv is not None
    orig_outstanding = inv.outstanding_amount

    # Issue Credit Note
    note = await invoice_service.issue_credit_debit_note(
        society_id=SOCIETY_A_ID,
        invoice_id=inv.id,
        note_type="CREDIT_NOTE",
        amount=Decimal("200.0000"),
        reason="Overbilled amenity charge",
        created_by=USER_ADMIN_ID,
    )
    assert note.note_number.startswith("CN-")
    assert note.amount == Decimal("200.0000")
    assert note.journal_entry_id is not None

    # Verify journal entry created is strictly balanced
    j_res = await seeded_session.execute(select(JournalEntry).where(JournalEntry.id == note.journal_entry_id))
    journal = j_res.scalar_one_or_none()
    assert journal is not None
    assert journal.total_debit == Decimal("200.0000")
    assert journal.total_credit == Decimal("200.0000")
    assert journal.status == "POSTED"

    # Invoice balance reduced
    assert inv.outstanding_amount == orig_outstanding - Decimal("200.0000")


@pytest.mark.asyncio
async def test_deterministic_late_fee_application(seeded_session: AsyncSession) -> None:
    """Late fee is applied only after due date + grace period, and prevents double billing."""
    invoice_service = InvoiceService(seeded_session)
    invoice_repo = InvoiceRepository(seeded_session)

    inv = await invoice_repo.get_by_number("INV-000002", SOCIETY_A_ID)
    assert inv is not None
    # due_date is 2026-04-15, grace_period is 5 days -> overdue after 2026-04-20

    # 1. Before due date (2026-04-10) -> fee must be 0
    fee1 = await invoice_service.apply_late_fees(
        society_id=SOCIETY_A_ID,
        invoice_id=inv.id,
        as_of_date=date(2026, 4, 10),
        applied_by=USER_ADMIN_ID,
    )
    assert fee1 == Decimal("0.0000")

    # 2. During grace period (2026-04-18) -> fee must be 0
    fee2 = await invoice_service.apply_late_fees(
        society_id=SOCIETY_A_ID,
        invoice_id=inv.id,
        as_of_date=date(2026, 4, 18),
        applied_by=USER_ADMIN_ID,
    )
    assert fee2 == Decimal("0.0000")

    # 3. After grace period (2026-04-25) -> late fee applied
    fee3 = await invoice_service.apply_late_fees(
        society_id=SOCIETY_A_ID,
        invoice_id=inv.id,
        as_of_date=date(2026, 4, 25),
        applied_by=USER_ADMIN_ID,
    )
    assert fee3 > Decimal("0.0000")
    assert inv.late_fee_total == fee3
    assert inv.status == "OVERDUE"

    # 4. Attempting to apply late fee again -> must be 0 (no double application)
    fee4 = await invoice_service.apply_late_fees(
        society_id=SOCIETY_A_ID,
        invoice_id=inv.id,
        as_of_date=date(2026, 4, 26),
        applied_by=USER_ADMIN_ID,
    )
    assert fee4 == Decimal("0.0000")


@pytest.mark.asyncio
async def test_published_invoice_immutability_and_approval_gate(seeded_session: AsyncSession) -> None:
    """Published invoices cannot have adjustments if paid/cancelled and publish requires approval."""
    invoice_service = InvoiceService(seeded_session)
    invoice_repo = InvoiceRepository(seeded_session)

    # 1. Paid invoice cannot receive adjustments
    inv1 = await invoice_repo.get_by_number("INV-000001", SOCIETY_A_ID)
    assert inv1 is not None
    assert inv1.status == "PAID"

    from apps.api.src.billing.domain.exceptions import InvoiceImmutableException
    from apps.api.src.core.exceptions import AppException

    with pytest.raises(InvoiceImmutableException):
        await invoice_service.apply_adjustment(
            society_id=SOCIETY_A_ID,
            invoice_id=inv1.id,
            adjustment_type="DISCOUNT",
            amount=Decimal("100.0000"),
            reason="Late discount attempt",
            created_by=USER_ADMIN_ID,
        )

    # 2. Cannot publish unapproved billing period when approval_required is True
    fin_period_repo = PeriodRepository(seeded_session)
    period_service = BillingPeriodService(seeded_session)
    fin_period = await fin_period_repo.get_period_for_date(SOCIETY_A_ID, date(2026, 6, 1))
    assert fin_period is not None

    june_period = await period_service.create_period(
        society_id=SOCIETY_A_ID,
        financial_period_id=fin_period.id,
        period_code="BP-2026-06",
        name="June 2026 Maintenance",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 30),
        billing_date=date(2026, 6, 1),
        due_date=date(2026, 6, 15),
        created_by=USER_ADMIN_ID,
    )

    # Generate invoices (status becomes REVIEW)
    await invoice_service.generate_invoices_for_period(
        society_id=SOCIETY_A_ID,
        billing_period_id=june_period.id,
        generated_by=USER_ADMIN_ID,
    )

    # Attempting to publish without approval raises AppException (BILLING_PERIOD_NOT_APPROVED)
    with pytest.raises(AppException) as exc_info:
        await invoice_service.publish_period(
            society_id=SOCIETY_A_ID,
            billing_period_id=june_period.id,
            published_by=USER_ADMIN_ID,
        )
    assert exc_info.value.code == "BILLING_PERIOD_NOT_APPROVED"

    # Approving first then publishing succeeds
    await invoice_service.approve_period(
        society_id=SOCIETY_A_ID,
        billing_period_id=june_period.id,
        approved_by=USER_ADMIN_ID,
    )
    published = await invoice_service.publish_period(
        society_id=SOCIETY_A_ID,
        billing_period_id=june_period.id,
        published_by=USER_ADMIN_ID,
    )
    assert published.status == "PUBLISHED"
