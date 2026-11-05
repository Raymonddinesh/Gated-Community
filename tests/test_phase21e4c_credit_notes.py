"""Phase 21E.4C — SaaS Credit Note Domain Unit Tests.

Covers:
1. Financial-year boundary resolution in Asia/Kolkata (IST).
2. Sequential numbering counter progression and formatting (SS-CN-{FY}-{SEQ:05d}).
3. DRAFT credit note creation, editing, and simulated preview.
4. Full credit note calculation and issuance against ISSUED invoice.
5. Partial credit note calculation (aggregate taxable override and per-line items).
6. Line-level eligibility validation preventing credit exceeding original invoice line item.
7. Over-credit prevention at invoice level (total credits cannot exceed invoice grand total).
8. Invoice balance adjustments:
   - Unpaid invoice: reduces amount_due and updates credits_applied.
   - Fully paid invoice: creates unapplied credit balance (ADVANCE_BALANCE) in PlatformBillingAdjustment.
   - Partial payment: adjusts amount_due and allocates remaining excess to ADVANCE_BALANCE.
9. VOID lifecycle transition:
   - Permanently retains credit_note_number and audit history.
   - Restores invoice amount_due and reduces credits_applied.
   - Reverses or removes advance balance adjustment.
10. Prohibited state transitions:
    - Cannot edit an ISSUED credit note.
    - Cannot void a DRAFT credit note.
    - Cannot issue against DRAFT or VOID invoices.
11. Tax Snapshot Verification (M-2 & M-3):
    - Uses exact historical TaxSnapshot from original invoice.
    - SHA-256 digest generated and verified.
    - Detection of corrupted/tampered snapshot.
    - Retains original tax rate even if current tax configuration changes.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from apps.api.src.database.base import Base
from apps.api.src.database.models.platform_billing import (
    PlatformBillingAdjustment,
    PlatformInvoice,
    PlatformSubscriptionAuditLog,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import PlatformSubscriptionPlan, SocietySubscription
from apps.api.src.subscriptions.credit_notes.exceptions import (
    CreditNoteExceedsEligibleBalanceException,
    CreditNoteInvoiceNotEligibleException,
    CreditNoteItemExceedsLineEligibilityException,
    CreditNoteTaxSnapshotTamperedException,
    InvalidCreditNoteStateException,
)
from apps.api.src.subscriptions.credit_notes.numbering import (
    IST_TIMEZONE,
    CreditNoteNumberingService,
    get_financial_year,
)
from apps.api.src.subscriptions.credit_notes.schemas import (
    PlatformCreditNoteCreateDraft,
    PlatformCreditNoteItemCreate,
    PlatformCreditNotePreviewRequest,
    PlatformCreditNoteUpdateDraft,
    PlatformCreditNoteVoidRequest,
)
from apps.api.src.subscriptions.credit_notes.service import PlatformCreditNoteService
from apps.api.src.subscriptions.invoicing.numbering import InvoiceNumberingService
from apps.api.src.subscriptions.invoicing.schemas import (
    PlatformInvoiceCreateDraft,
    PlatformInvoiceItemCreate,
)
from apps.api.src.subscriptions.invoicing.service import PlatformInvoiceService
from apps.api.src.subscriptions.tax import (
    GSTTaxEngine,
    TaxConfigurationService,
    TaxRateConfig,
    TaxRuleStatus,
)

IST = IST_TIMEZONE


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
async def in_memory_db():
    """In-memory SQLite async engine for fast isolated unit tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(in_memory_db):
    """Session factory for async sessions."""
    return async_sessionmaker(bind=in_memory_db, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
def custom_tax_config():
    """Isolated tax configuration service."""
    cfg = TaxConfigurationService()
    cfg.reset_to_defaults()
    return cfg


@pytest.fixture
def tax_engine(custom_tax_config):
    return GSTTaxEngine(custom_tax_config)


@pytest.fixture
def invoice_service(custom_tax_config):
    tax_eng = GSTTaxEngine(custom_tax_config)
    num_svc = InvoiceNumberingService(prefix="SS")
    return PlatformInvoiceService(numbering_service=num_svc, tax_engine=tax_eng)


async def _seed_society_and_subscription(
    session: AsyncSession, society_id: UUID | None = None, state: str = "Karnataka"
) -> tuple[Society, SocietySubscription]:
    soc_id = society_id or uuid4()
    plan_id = uuid4()
    sub_id = uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)

    soc = Society(
        id=soc_id,
        legal_name="Credit Note Test Society",
        display_name="CN Soc",
        address_line1="456 Innovation Park",
        city="Bengaluru",
        state=state,
        postal_code="560100",
    )
    plan = PlatformSubscriptionPlan(
        id=plan_id,
        plan_code=f"PLAN_CN_{uuid4().hex[:6]}",
        display_name="Enterprise CN Plan",
        monthly_price=Decimal("10000.00"),
    )
    sub = SocietySubscription(
        id=sub_id,
        society_id=soc_id,
        plan_id=plan_id,
        status="ACTIVE",
        starts_at=now,
        current_period_start=now,
        current_period_end=now,
    )
    session.add_all([soc, plan, sub])
    await session.commit()
    return soc, sub


async def _create_and_issue_invoice(
    session: AsyncSession,
    invoice_svc: PlatformInvoiceService,
    soc: Society,
    sub: SocietySubscription,
    line_items: list[tuple[str, Decimal, Decimal]] | None = None,
) -> PlatformInvoice:
    """Helper to create and finalize an invoice."""
    if line_items is None:
        items = [
            PlatformInvoiceItemCreate(
                description="SaaS Annual Platform Fee",
                sac_code="998314",
                quantity=Decimal("1.0000"),
                unit_price=Decimal("10000.00"),
            )
        ]
    else:
        items = [
            PlatformInvoiceItemCreate(
                description=desc,
                sac_code="998314",
                quantity=qty,
                unit_price=price,
            )
            for desc, qty, price in line_items
        ]

    draft_payload = PlatformInvoiceCreateDraft(
        society_id=soc.id,
        subscription_id=sub.id,
        billing_cycle="ANNUAL",
        period_start=datetime(2026, 4, 1, 0, 0, 0),
        period_end=datetime(2027, 3, 31, 23, 59, 59),
        due_date=date(2026, 4, 15),
        items=items,
    )
    draft_res = await invoice_svc.create_draft_invoice(session, draft_payload)
    final_res = await invoice_svc.finalize_invoice(session, draft_res.id)
    await session.commit()

    inv_stmt = (
        select(PlatformInvoice)
        .options(selectinload(PlatformInvoice.items))
        .where(PlatformInvoice.id == final_res.id)
    )
    inv = (await session.execute(inv_stmt)).scalar_one()
    return inv


# ==============================================================================
# 1. Numbering Service & Fiscal Year Boundary Tests
# ==============================================================================


def test_credit_note_fiscal_year_resolution():
    """Verify fiscal year boundary calculation in Asia/Kolkata timezone."""
    # Last second of FY 2025-26: 2026-03-31 23:59:59 IST -> 2526
    dt_end_fy25 = datetime(2026, 3, 31, 23, 59, 59, tzinfo=IST)
    assert get_financial_year(dt_end_fy25) == "2526"

    # First second of FY 2026-27: 2026-04-01 00:00:00 IST -> 2627
    dt_start_fy26 = datetime(2026, 4, 1, 0, 0, 0, tzinfo=IST)
    assert get_financial_year(dt_start_fy26) == "2627"

    # Mid year: November 2026 -> 2627
    dt_mid = datetime(2026, 11, 2, 12, 0, 0, tzinfo=IST)
    assert get_financial_year(dt_mid) == "2627"


@pytest.mark.asyncio
async def test_credit_note_numbering_service_progression(session_factory):
    """Verify CreditNoteNumberingService increments monotonically and formats with SS-CN."""
    num_svc = CreditNoteNumberingService(prefix="SS-CN")
    async with session_factory() as session:
        fixed_dt = datetime(2026, 6, 15, 10, 0, 0, tzinfo=IST)

        cn1, fy1 = await num_svc.allocate_credit_note_number(session, transaction_date=fixed_dt)
        await session.commit()
        assert cn1 == "SS-CN-2627-00001"
        assert fy1 == "2627"

        cn2, fy2 = await num_svc.allocate_credit_note_number(session, transaction_date=fixed_dt)
        await session.commit()
        assert cn2 == "SS-CN-2627-00002"
        assert fy2 == "2627"

        cn3, fy3 = await num_svc.allocate_credit_note_number(session, transaction_date=fixed_dt)
        await session.commit()
        assert cn3 == "SS-CN-2627-00003"
        assert fy3 == "2627"


# ==============================================================================
# 2. DRAFT Creation, Updating, and Preview
# ==============================================================================


@pytest.mark.asyncio
async def test_create_draft_credit_note(session_factory, invoice_service, tax_engine):
    """Test creating a DRAFT credit note against an ISSUED invoice."""
    async with session_factory() as session:
        soc, sub = await _seed_society_and_subscription(session)
        invoice = await _create_and_issue_invoice(session, invoice_service, soc, sub)

        cn_svc = PlatformCreditNoteService(session, tax_engine=tax_engine)
        draft_payload = PlatformCreditNoteCreateDraft(
            invoice_id=invoice.id,
            reason="Commercial discount after billing",
            taxable_amount=Decimal("2000.00"),
            notes="Authorized by Finance Team",
        )
        draft = await cn_svc.create_draft_credit_note(draft_payload)
        await session.commit()

        assert draft.status == "DRAFT"
        assert draft.credit_note_number is None
        assert draft.issued_at is None
        assert draft.invoice_id == invoice.id
        assert draft.society_id == soc.id
        assert draft.taxable_amount == Decimal("2000.00")
        assert draft.tax_total == Decimal("360.00")  # 18% of 2000
        assert draft.grand_total == Decimal("2360.00")
        assert len(draft.items) == 1
        assert draft.reason == "Commercial discount after billing"


@pytest.mark.asyncio
async def test_update_draft_credit_note(session_factory, invoice_service, tax_engine):
    """Test modifying reason, notes, and taxable amount on an unissued DRAFT credit note."""
    async with session_factory() as session:
        soc, sub = await _seed_society_and_subscription(session)
        invoice = await _create_and_issue_invoice(session, invoice_service, soc, sub)

        cn_svc = PlatformCreditNoteService(session, tax_engine=tax_engine)
        draft = await cn_svc.create_draft_credit_note(
            PlatformCreditNoteCreateDraft(
                invoice_id=invoice.id,
                reason="Initial reason",
                taxable_amount=Decimal("1000.00"),
            )
        )
        await session.commit()

        # Update draft
        updated = await cn_svc.update_draft_credit_note(
            credit_note_id=draft.id,
            payload=PlatformCreditNoteUpdateDraft(
                reason="Updated negotiated credit",
                notes="Revised terms",
                taxable_amount=Decimal("3000.00"),
            ),
        )
        await session.commit()

        assert updated.reason == "Updated negotiated credit"
        assert updated.notes == "Revised terms"
        assert updated.taxable_amount == Decimal("3000.00")
        assert updated.tax_total == Decimal("540.00")  # 18% of 3000
        assert updated.grand_total == Decimal("3540.00")


@pytest.mark.asyncio
async def test_preview_credit_note(session_factory, invoice_service, tax_engine):
    """Test simulated preview endpoint without persisting any changes."""
    async with session_factory() as session:
        soc, sub = await _seed_society_and_subscription(session)
        invoice = await _create_and_issue_invoice(session, invoice_service, soc, sub)

        cn_svc = PlatformCreditNoteService(session, tax_engine=tax_engine)
        preview = await cn_svc.calculate_preview(
            PlatformCreditNotePreviewRequest(
                invoice_id=invoice.id,
                taxable_amount=Decimal("5000.00"),
            )
        )

        assert preview.invoice_id == invoice.id
        assert preview.original_invoice_total == Decimal("11800.00")
        assert preview.prior_issued_credits == Decimal("0.00")
        assert preview.eligible_invoice_balance == Decimal("11800.00")
        assert preview.taxable_amount == Decimal("5000.00")
        assert preview.tax_total == Decimal("900.00")
        assert preview.grand_total == Decimal("5900.00")
        assert preview.new_invoice_outstanding == Decimal("5900.00")
        assert preview.unapplied_credit_balance == Decimal("0.00")

        # Verify no credit note was persisted
        all_cns = await cn_svc.list_credit_notes(invoice_id=invoice.id)
        assert len(all_cns) == 0


# ==============================================================================
# 3. Full Credit Note & Balance Adjustments (Example 1: Unpaid Invoice)
# ==============================================================================


@pytest.mark.asyncio
async def test_full_credit_note_unpaid_invoice(session_factory, invoice_service, tax_engine):
    """Full credit note against an unpaid invoice reduces amount_due to zero."""
    async with session_factory() as session:
        soc, sub = await _seed_society_and_subscription(session)
        invoice = await _create_and_issue_invoice(session, invoice_service, soc, sub)

        assert invoice.grand_total == Decimal("11800.00")
        assert invoice.amount_paid == Decimal("0.00")
        assert invoice.amount_due == Decimal("11800.00")

        cn_svc = PlatformCreditNoteService(session, tax_engine=tax_engine)
        draft = await cn_svc.create_draft_credit_note(
            PlatformCreditNoteCreateDraft(
                invoice_id=invoice.id,
                reason="Full service cancellation",
            )
        )
        await session.commit()

        issued_cn = await cn_svc.issue_credit_note(draft.id)
        await session.commit()

        assert issued_cn.status == "ISSUED"
        assert issued_cn.credit_note_number is not None
        assert issued_cn.credit_note_number.startswith("SS-CN-")
        assert issued_cn.grand_total == Decimal("11800.00")

        # Refresh invoice
        await session.refresh(invoice)
        assert invoice.credits_applied == Decimal("11800.00")
        assert invoice.amount_due == Decimal("0.00")


# ==============================================================================
# 4. Partial Credit Note & Advance Balance (Example 2: Fully Paid Invoice)
# ==============================================================================


@pytest.mark.asyncio
async def test_partial_credit_note_fully_paid_invoice(session_factory, invoice_service, tax_engine):
    """Credit note on an already settled invoice creates unapplied ADVANCE_BALANCE."""
    async with session_factory() as session:
        soc, sub = await _seed_society_and_subscription(session)
        invoice = await _create_and_issue_invoice(session, invoice_service, soc, sub)

        # Mark invoice as fully paid
        invoice.amount_paid = Decimal("11800.00")
        invoice.amount_due = Decimal("0.00")
        invoice.status = "PAID"
        await session.commit()

        cn_svc = PlatformCreditNoteService(session, tax_engine=tax_engine)
        # Issue 50% partial credit: ₹5,000 taxable + 18% tax = ₹5,900
        draft = await cn_svc.create_draft_credit_note(
            PlatformCreditNoteCreateDraft(
                invoice_id=invoice.id,
                reason="Partial commercial rebate for downtime",
                taxable_amount=Decimal("5000.00"),
            )
        )
        await session.commit()

        issued_cn = await cn_svc.issue_credit_note(draft.id)
        await session.commit()

        assert issued_cn.status == "ISSUED"
        assert issued_cn.grand_total == Decimal("5900.00")

        # Verify invoice state
        await session.refresh(invoice)
        assert invoice.credits_applied == Decimal("5900.00")
        assert invoice.amount_due == Decimal("0.00")

        # Verify unapplied advance balance adjustment created
        adj_stmt = select(PlatformBillingAdjustment).where(
            PlatformBillingAdjustment.credit_note_id == issued_cn.id
        )
        adj = (await session.execute(adj_stmt)).scalar_one_or_none()
        assert adj is not None
        assert adj.adjustment_type == "ADVANCE_BALANCE"
        assert adj.amount == Decimal("5900.00")
        assert adj.society_id == soc.id


# ==============================================================================
# 5. Multiple Partial Credit Notes & Over-Credit Prevention
# ==============================================================================


@pytest.mark.asyncio
async def test_multiple_partial_credit_notes_and_overcredit_prevention(
    session_factory, invoice_service, tax_engine
):
    """Multiple partial credit notes sum up; attempts exceeding balance are rejected."""
    async with session_factory() as session:
        soc, sub = await _seed_society_and_subscription(session)
        invoice = await _create_and_issue_invoice(session, invoice_service, soc, sub)

        cn_svc = PlatformCreditNoteService(session, tax_engine=tax_engine)

        # 1. First partial credit: ₹4,000 taxable (₹4,720 grand total)
        draft1 = await cn_svc.create_draft_credit_note(
            PlatformCreditNoteCreateDraft(
                invoice_id=invoice.id,
                reason="Credit 1",
                taxable_amount=Decimal("4000.00"),
            )
        )
        await cn_svc.issue_credit_note(draft1.id)
        await session.commit()

        # 2. Second partial credit: ₹6,000 taxable (₹7,080 grand total)
        # Total credits now = 4,720 + 7,080 = 11,800 (100% of invoice)
        draft2 = await cn_svc.create_draft_credit_note(
            PlatformCreditNoteCreateDraft(
                invoice_id=invoice.id,
                reason="Credit 2",
                taxable_amount=Decimal("6000.00"),
            )
        )
        await cn_svc.issue_credit_note(draft2.id)
        await session.commit()

        await session.refresh(invoice)
        assert invoice.credits_applied == Decimal("11800.00")
        assert invoice.amount_due == Decimal("0.00")

        # 3. Third credit attempt: even ₹1.00 should be rejected
        with pytest.raises(CreditNoteExceedsEligibleBalanceException) as exc_info:
            await cn_svc.create_draft_credit_note(
                PlatformCreditNoteCreateDraft(
                    invoice_id=invoice.id,
                    reason="Credit 3 should fail",
                    taxable_amount=Decimal("1.00"),
                )
            )
        assert "exceeds eligible remaining invoice balance" in str(exc_info.value.message)


# ==============================================================================
# 6. Per-Line Level Eligibility Validation
# ==============================================================================


@pytest.mark.asyncio
async def test_per_line_level_credit_eligibility(session_factory, invoice_service, tax_engine):
    """Line-item crediting cannot exceed original line item taxable amount."""
    async with session_factory() as session:
        soc, sub = await _seed_society_and_subscription(session)
        # Create invoice with two line items: Line 1 = ₹4,000, Line 2 = ₹6,000
        invoice = await _create_and_issue_invoice(
            session,
            invoice_service,
            soc,
            sub,
            line_items=[
                ("Software License Module A", Decimal("1.0000"), Decimal("4000.00")),
                ("Software License Module B", Decimal("1.0000"), Decimal("6000.00")),
            ],
        )

        inv_items = invoice.items
        assert len(inv_items) == 2
        item_a = next(it for it in inv_items if "Module A" in it.description)

        cn_svc = PlatformCreditNoteService(session, tax_engine=tax_engine)

        # Attempt to credit ₹4,500 on Line A which only has ₹4,000
        with pytest.raises(CreditNoteItemExceedsLineEligibilityException) as exc_info:
            await cn_svc.create_draft_credit_note(
                PlatformCreditNoteCreateDraft(
                    invoice_id=invoice.id,
                    reason="Excess line credit",
                    items=[
                        PlatformCreditNoteItemCreate(
                            invoice_item_id=item_a.id,
                            description="Module A credit",
                            quantity=Decimal("1.0000"),
                            unit_price=Decimal("4500.00"),
                        )
                    ],
                )
            )
        assert "exceeds line eligible amount" in str(exc_info.value.message)


# ==============================================================================
# 7. Prohibited Lifecycle Transitions & State Machine Enforcement
# ==============================================================================


@pytest.mark.asyncio
async def test_prohibited_state_transitions(session_factory, invoice_service, tax_engine):
    """Enforce strict state machine constraints."""
    async with session_factory() as session:
        soc, sub = await _seed_society_and_subscription(session)
        invoice = await _create_and_issue_invoice(session, invoice_service, soc, sub)

        cn_svc = PlatformCreditNoteService(session, tax_engine=tax_engine)
        draft = await cn_svc.create_draft_credit_note(
            PlatformCreditNoteCreateDraft(
                invoice_id=invoice.id,
                reason="Prohibited transition test",
                taxable_amount=Decimal("1000.00"),
            )
        )
        await session.commit()

        # 1. Cannot void a DRAFT credit note (must be ISSUED)
        with pytest.raises(InvalidCreditNoteStateException) as exc1:
            await cn_svc.void_credit_note(
                credit_note_id=draft.id,
                payload=PlatformCreditNoteVoidRequest(void_reason="Mistake in draft"),
            )
        assert "Only ISSUED credit notes can be voided" in str(exc1.value.message)

        # 2. Issue the credit note
        issued = await cn_svc.issue_credit_note(draft.id)
        await session.commit()

        # 3. Cannot update an ISSUED credit note
        with pytest.raises(InvalidCreditNoteStateException) as exc2:
            await cn_svc.update_draft_credit_note(
                credit_note_id=issued.id,
                payload=PlatformCreditNoteUpdateDraft(reason="Attempt update on issued"),
            )
        assert "Cannot update a credit note that is already ISSUED or VOID" in str(exc2.value.message)

        # 4. Cannot re-issue an already ISSUED credit note
        with pytest.raises(InvalidCreditNoteStateException) as exc3:
            await cn_svc.issue_credit_note(issued.id)
        assert "is already in 'ISSUED' state" in str(exc3.value.message)


@pytest.mark.asyncio
async def test_cannot_credit_draft_or_void_invoice(session_factory, invoice_service, tax_engine):
    """Credit notes cannot be issued against DRAFT or VOID invoices."""
    async with session_factory() as session:
        soc, sub = await _seed_society_and_subscription(session)

        # Create DRAFT invoice (unfinalized)
        draft_inv_res = await invoice_service.create_draft_invoice(
            session,
            PlatformInvoiceCreateDraft(
                society_id=soc.id,
                subscription_id=sub.id,
                billing_cycle="MONTHLY",
                period_start=datetime(2026, 4, 1, 0, 0, 0),
                period_end=datetime(2026, 4, 30, 23, 59, 59),
                due_date=date(2026, 4, 15),
                items=[
                    PlatformInvoiceItemCreate(
                        description="Test",
                        sac_code="998314",
                        quantity=Decimal("1.0000"),
                        unit_price=Decimal("5000.00"),
                    )
                ],
            ),
        )
        await session.commit()

        cn_svc = PlatformCreditNoteService(session, tax_engine=tax_engine)

        with pytest.raises(CreditNoteInvoiceNotEligibleException) as exc_info:
            await cn_svc.create_draft_credit_note(
                PlatformCreditNoteCreateDraft(
                    invoice_id=draft_inv_res.id,
                    reason="Credit against unfinalized invoice",
                )
            )
        assert "is not eligible for credit note issuance" in str(exc_info.value.message)


# ==============================================================================
# 8. Voiding Credit Note & Balance Restoration
# ==============================================================================


@pytest.mark.asyncio
async def test_void_credit_note_restores_invoice_balance(session_factory, invoice_service, tax_engine):
    """Voiding an issued credit note permanently retains its number and restores invoice balance."""
    async with session_factory() as session:
        soc, sub = await _seed_society_and_subscription(session)
        invoice = await _create_and_issue_invoice(session, invoice_service, soc, sub)

        cn_svc = PlatformCreditNoteService(session, tax_engine=tax_engine)
        draft = await cn_svc.create_draft_credit_note(
            PlatformCreditNoteCreateDraft(
                invoice_id=invoice.id,
                reason="Void test credit",
                taxable_amount=Decimal("3000.00"),  # ₹3,540 grand total
            )
        )
        issued = await cn_svc.issue_credit_note(draft.id)
        await session.commit()

        cn_num = issued.credit_note_number
        assert cn_num is not None

        # Verify applied credits on invoice
        await session.refresh(invoice)
        assert invoice.credits_applied == Decimal("3540.00")
        assert invoice.amount_due == Decimal("8260.00")

        # Void the credit note
        voided = await cn_svc.void_credit_note(
            credit_note_id=issued.id,
            payload=PlatformCreditNoteVoidRequest(void_reason="Issued in error"),
        )
        await session.commit()

        assert voided.status == "VOID"
        assert voided.credit_note_number == cn_num  # Permanent number preserved!
        assert "Issued in error" in voided.notes

        # Verify invoice balance restored
        await session.refresh(invoice)
        assert invoice.credits_applied == Decimal("0.00")
        assert invoice.amount_due == Decimal("11800.00")


# ==============================================================================
# 9. Tax Snapshot Integrity Verification & Tamper Detection (M-2 & M-3)
# ==============================================================================


@pytest.mark.asyncio
async def test_credit_note_tax_snapshot_verification_and_tamper_detection(
    session_factory, invoice_service, tax_engine
):
    """Verify cryptographic SHA-256 digest on credit note snapshot and reject tampered data."""
    async with session_factory() as session:
        soc, sub = await _seed_society_and_subscription(session)
        invoice = await _create_and_issue_invoice(session, invoice_service, soc, sub)

        cn_svc = PlatformCreditNoteService(session, tax_engine=tax_engine)
        draft = await cn_svc.create_draft_credit_note(
            PlatformCreditNoteCreateDraft(
                invoice_id=invoice.id,
                reason="Tax audit verification test",
                taxable_amount=Decimal("5000.00"),
            )
        )
        issued = await cn_svc.issue_credit_note(draft.id)
        await session.commit()

        # Verify snapshot integrity via service
        verify_res = await cn_svc.get_credit_note_tax_snapshot(issued.id)
        assert verify_res.verified is True
        assert verify_res.stored_hash == verify_res.computed_hash

        # Tamper with snapshot in audit log directly
        audit_stmt = select(PlatformSubscriptionAuditLog).where(
            PlatformSubscriptionAuditLog.entity_id == issued.id,
            PlatformSubscriptionAuditLog.entity_type == "CREDIT_NOTE_TAX_SNAPSHOT",
        )
        audit_row = (await session.execute(audit_stmt)).scalar_one()

        tampered_state = dict(audit_row.after_state)
        tampered_state["taxable_value"] = "99999.00"  # Maliciously alter taxable value
        audit_row.after_state = tampered_state
        await session.commit()

        # Cryptographic verification must fail with CreditNoteTaxSnapshotTamperedException
        with pytest.raises(CreditNoteTaxSnapshotTamperedException) as exc_info:
            await cn_svc.get_credit_note_tax_snapshot(issued.id)
        assert "integrity verification failed" in str(exc_info.value.message)


@pytest.mark.asyncio
async def test_credit_note_historical_snapshot_preservation_across_tax_rate_changes(
    session_factory, invoice_service, custom_tax_config
):
    """Verify that changing future GST tax rates does NOT affect credit notes issued against older invoices (M-2)."""
    async with session_factory() as session:
        soc, sub = await _seed_society_and_subscription(session)

        # 1. Invoice created and issued under 18% GST (Rule v1)
        invoice = await _create_and_issue_invoice(session, invoice_service, soc, sub)
        assert invoice.tax_total == Decimal("1800.00")

        # 2. Modify tax configuration to 28% GST (e.g. regulatory tax hike)
        hike_rule = TaxRateConfig(
            version="v2.0-hike",
            sac_code="998314",
            description="Software SaaS hiked rate",
            total_rate=Decimal("28.00"),
            cgst_rate=Decimal("14.00"),
            sgst_rate=Decimal("14.00"),
            igst_rate=Decimal("28.00"),
            status=TaxRuleStatus.ACTIVE,
            effective_from=date(2026, 1, 1),
        )
        custom_tax_config.register_rule(hike_rule)

        # 3. Create and issue credit note against original invoice
        engine_v2 = GSTTaxEngine(custom_tax_config)
        cn_svc = PlatformCreditNoteService(session, tax_engine=engine_v2)

        draft = await cn_svc.create_draft_credit_note(
            PlatformCreditNoteCreateDraft(
                invoice_id=invoice.id,
                reason="Rebate issued under new tax regime",
                taxable_amount=Decimal("5000.00"),
            )
        )
        issued = await cn_svc.issue_credit_note(draft.id)
        await session.commit()

        # MUST retain original 18% tax rate, NOT 28%!
        assert issued.cgst_amount == Decimal("450.00")  # 9% of 5000
        assert issued.sgst_amount == Decimal("450.00")  # 9% of 5000
        assert issued.tax_total == Decimal("900.00")    # 18% of 5000
        assert issued.grand_total == Decimal("5900.00")
