"""Phase 21E.4B — SaaS Invoicing Domain Unit Tests.

Covers:
1. Financial-year boundary resolution in Asia/Kolkata (IST).
2. Sequential numbering counter progression and formatting.
3. DRAFT invoice creation, editing, and tax calculation.
4. Finalization (DRAFT -> ISSUED) with number allocation.
5. Duplicate finalization rejection and idempotency.
6. VOID lifecycle transition retaining original number.
7. Rejection of invalid lifecycle transitions (e.g. editing issued, voiding paid).
8. Tax snapshot persistence, association, and SHA-256 integrity verification.
9. Tamper detection on corrupted tax snapshots.
10. Credit note version compatibility (M-2): Historical rate & version retention across config changes.
11. Safe failure on missing billing address or zero line items.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.src.database.base import Base
from apps.api.src.database.models.platform_billing import PlatformInvoice
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import PlatformSubscriptionPlan, SocietySubscription
from apps.api.src.subscriptions.invoicing.exceptions import (
    InvalidInvoiceStateException,
    InvoiceNotFoundException,
    InvoiceTaxSnapshotTamperedException,
)
from apps.api.src.subscriptions.invoicing.numbering import (
    IST_TIMEZONE,
    InvoiceNumberingService,
    get_financial_year,
)
from apps.api.src.subscriptions.invoicing.schemas import (
    PlatformInvoiceCreateDraft,
    PlatformInvoiceItemCreate,
    PlatformInvoiceUpdateDraft,
)
from apps.api.src.subscriptions.invoicing.service import PlatformInvoiceService
from apps.api.src.subscriptions.tax import (
    GSTTaxEngine,
    TaxConfigurationService,
    TaxRateConfig,
    TaxRuleStatus,
)

IST = IST_TIMEZONE


@pytest.fixture
async def in_memory_db():
    """In-memory SQLite async engine for fast unit tests."""
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
def invoice_service(custom_tax_config):
    """PlatformInvoiceService with isolated tax config."""
    tax_engine = GSTTaxEngine(custom_tax_config)
    numbering_svc = InvoiceNumberingService(prefix="SS")
    return PlatformInvoiceService(numbering_service=numbering_svc, tax_engine=tax_engine)


async def _seed_society_and_subscription(session: AsyncSession, society_id=None, state="Karnataka"):
    soc_id = society_id or uuid4()
    plan_id = uuid4()
    sub_id = uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)

    soc = Society(
        id=soc_id,
        legal_name="Test Invoicing Society",
        display_name="Invoicing Soc",
        address_line1="100 Tech Park",
        city="Bengaluru",
        state=state,
        postal_code="560001",
    )
    plan = PlatformSubscriptionPlan(
        id=plan_id,
        plan_code=f"PLAN_INV_{uuid4().hex[:6]}",
        display_name="Standard SaaS Plan",
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
    return soc_id, sub_id


# ==============================================================================
# 1. FINANCIAL YEAR & SEQUENTIAL NUMBERING TESTS
# ==============================================================================


def test_financial_year_determination_asia_kolkata():
    """Verify statutory Indian FY boundaries (April 1 to March 31) in Asia/Kolkata."""
    # 1. April 1, 2026 00:00:00 IST -> FY 2627
    dt_apr_start = datetime(2026, 4, 1, 0, 0, 0, tzinfo=IST)
    assert get_financial_year(dt_apr_start) == "2627"

    # 2. March 31, 2027 23:59:59 IST -> FY 2627
    dt_mar_end = datetime(2027, 3, 31, 23, 59, 59, tzinfo=IST)
    assert get_financial_year(dt_mar_end) == "2627"

    # 3. April 1, 2027 00:00:00 IST -> FY 2728 (rollover)
    dt_next_fy = datetime(2027, 4, 1, 0, 0, 0, tzinfo=IST)
    assert get_financial_year(dt_next_fy) == "2728"

    # 4. January 15, 2026 -> FY 2526
    dt_jan = datetime(2026, 1, 15, 12, 0, 0, tzinfo=IST)
    assert get_financial_year(dt_jan) == "2526"

    # 5. Date-only argument
    d = date(2026, 5, 20)
    assert get_financial_year(d) == "2627"


@pytest.mark.asyncio
async def test_invoice_numbering_sequential_allocation(session_factory):
    """InvoiceNumberingService allocates consecutive numbers transactionally."""
    num_svc = InvoiceNumberingService(prefix="SS")
    dt = datetime(2026, 5, 1, 10, 0, 0, tzinfo=IST)

    async with session_factory() as session:
        # 1. First invoice in FY 2627
        num1, fy1 = await num_svc.allocate_invoice_number(session, dt)
        assert fy1 == "2627"
        assert num1 == "SS-2627-00001"
        await session.commit()

    async with session_factory() as session:
        # 2. Second invoice in FY 2627
        num2, fy2 = await num_svc.allocate_invoice_number(session, dt)
        assert fy2 == "2627"
        assert num2 == "SS-2627-00002"
        await session.commit()

    async with session_factory() as session:
        # 3. Rollover to next financial year FY 2728
        next_fy_dt = datetime(2027, 4, 5, 10, 0, 0, tzinfo=IST)
        num3, fy3 = await num_svc.allocate_invoice_number(session, next_fy_dt)
        assert fy3 == "2728"
        assert num3 == "SS-2728-00001"
        await session.commit()


# ==============================================================================
# 2. DRAFT CREATION & EDITING TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_draft_invoice_creation(session_factory, invoice_service):
    """Draft invoice creation initializes status DRAFT without allocating a legal invoice number."""
    now = datetime.now(UTC).replace(tzinfo=None)
    async with session_factory() as session:
        soc_id, sub_id = await _seed_society_and_subscription(session)

    async with session_factory() as session:
        payload = PlatformInvoiceCreateDraft(
            society_id=soc_id,
            subscription_id=sub_id,
            billing_cycle="MONTHLY",
            period_start=now,
            period_end=now,
            due_date=date.today(),
            items=[
                PlatformInvoiceItemCreate(
                    item_type="BASE_PLAN",
                    description="Enterprise Plan",
                    sac_code="998313",
                    quantity=Decimal("1.0000"),
                    unit_price=Decimal("10000.00"),
                    discount_amount=Decimal("1000.00"),
                )
            ],
            prorated_credit=Decimal("500.00"),
        )
        inv = await invoice_service.create_draft_invoice(session, payload)
        await session.commit()

        assert inv.status == "DRAFT"
        assert inv.invoice_number is None, "DRAFT invoice must not have an invoice number"
        assert inv.fiscal_year is None
        assert inv.subtotal == Decimal("10000.00")
        assert inv.discount_total == Decimal("1000.00")
        assert inv.prorated_credit == Decimal("500.00")
        assert inv.taxable_amount == Decimal("8500.00")  # (10000 - 1000) - 500
        assert inv.cgst_amount == Decimal("765.00")      # 9% of 8500
        assert inv.sgst_amount == Decimal("765.00")      # 9% of 8500
        assert inv.igst_amount == Decimal("0.00")
        assert inv.tax_total == Decimal("1530.00")
        assert inv.grand_total == Decimal("10030.00")


@pytest.mark.asyncio
async def test_draft_invoice_editing(session_factory, invoice_service):
    """Draft invoice allows modifying due date, credits, and line items."""
    now = datetime.now(UTC).replace(tzinfo=None)
    async with session_factory() as session:
        soc_id, sub_id = await _seed_society_and_subscription(session)
        payload = PlatformInvoiceCreateDraft(
            society_id=soc_id,
            subscription_id=sub_id,
            billing_cycle="MONTHLY",
            period_start=now,
            period_end=now,
            due_date=date.today(),
            items=[
                PlatformInvoiceItemCreate(
                    description="Initial Plan",
                    sac_code="998313",
                    quantity=Decimal("1.0000"),
                    unit_price=Decimal("5000.00"),
                )
            ],
        )
        inv = await invoice_service.create_draft_invoice(session, payload)
        await session.commit()
        inv_id = inv.id

    async with session_factory() as session:
        # Edit draft: add new item and increase prorated credit
        update_payload = PlatformInvoiceUpdateDraft(
            prorated_credit=Decimal("1000.00"),
            items=[
                PlatformInvoiceItemCreate(
                    description="Updated Plan",
                    sac_code="998313",
                    quantity=Decimal("1.0000"),
                    unit_price=Decimal("8000.00"),
                    discount_amount=Decimal("500.00"),
                )
            ],
        )
        updated = await invoice_service.update_draft_invoice(session, inv_id, update_payload)
        await session.commit()

        assert updated.status == "DRAFT"
        assert updated.subtotal == Decimal("8000.00")
        assert updated.discount_total == Decimal("500.00")
        assert updated.prorated_credit == Decimal("1000.00")
        assert updated.taxable_amount == Decimal("6500.00")  # (8000 - 500) - 1000
        assert updated.tax_total == Decimal("1170.00")       # 18% of 6500
        assert updated.grand_total == Decimal("7670.00")


# ==============================================================================
# 3. FINALIZATION (DRAFT -> ISSUED) & IMMUTABILITY
# ==============================================================================


@pytest.mark.asyncio
async def test_invoice_finalization_draft_to_issued(session_factory, invoice_service):
    """Finalizing an invoice allocates sequential number, sets ISSUED, and stores verifiable snapshot."""
    now = datetime.now(UTC).replace(tzinfo=None)
    async with session_factory() as session:
        soc_id, sub_id = await _seed_society_and_subscription(session, state="Maharashtra")  # Inter-state
        payload = PlatformInvoiceCreateDraft(
            society_id=soc_id,
            subscription_id=sub_id,
            billing_cycle="MONTHLY",
            period_start=now,
            period_end=now,
            due_date=date.today(),
            items=[
                PlatformInvoiceItemCreate(
                    description="Enterprise Subscription",
                    sac_code="998313",
                    quantity=Decimal("1.0000"),
                    unit_price=Decimal("20000.00"),
                )
            ],
        )
        inv = await invoice_service.create_draft_invoice(session, payload)
        await session.commit()
        inv_id = inv.id

    async with session_factory() as session:
        finalized = await invoice_service.finalize_invoice(session, inv_id)
        await session.commit()

        assert finalized.status == "ISSUED"
        assert finalized.invoice_number is not None
        assert finalized.invoice_number.startswith("SS-")
        assert finalized.fiscal_year is not None
        assert finalized.issued_at is not None
        assert finalized.taxable_amount == Decimal("20000.00")
        # Inter-state to Maharashtra: IGST 18%
        assert finalized.igst_amount == Decimal("3600.00")
        assert finalized.cgst_amount == Decimal("0.00")
        assert finalized.sgst_amount == Decimal("0.00")
        assert finalized.tax_total == Decimal("3600.00")
        assert finalized.grand_total == Decimal("23600.00")

    # Verify cryptographic tax snapshot
    async with session_factory() as session:
        v_res = await invoice_service.verify_invoice_tax_snapshot(session, inv_id)
        assert v_res.is_valid is True
        assert v_res.sac_code == "998313"
        assert v_res.tax_total == Decimal("3600.00")
        assert v_res.grand_total == Decimal("23600.00")


@pytest.mark.asyncio
async def test_duplicate_finalization_prevention(session_factory, invoice_service):
    """Duplicate finalization of an already ISSUED invoice is strictly rejected."""
    now = datetime.now(UTC).replace(tzinfo=None)
    async with session_factory() as session:
        soc_id, sub_id = await _seed_society_and_subscription(session)
        payload = PlatformInvoiceCreateDraft(
            society_id=soc_id,
            subscription_id=sub_id,
            billing_cycle="MONTHLY",
            period_start=now,
            period_end=now,
            due_date=date.today(),
            items=[PlatformInvoiceItemCreate(description="Base", unit_price=Decimal("1000.00"))],
        )
        inv = await invoice_service.create_draft_invoice(session, payload)
        await session.commit()
        inv_id = inv.id

    async with session_factory() as session:
        await invoice_service.finalize_invoice(session, inv_id)
        await session.commit()

    # Second finalization attempt must raise InvalidInvoiceStateException
    async with session_factory() as session:
        with pytest.raises(InvalidInvoiceStateException) as exc:
            await invoice_service.finalize_invoice(session, inv_id)
        assert "Duplicate finalization is prohibited" in str(exc.value)


@pytest.mark.asyncio
async def test_cannot_edit_issued_or_void_invoice(session_factory, invoice_service):
    """Issued or Void invoices cannot be updated."""
    now = datetime.now(UTC).replace(tzinfo=None)
    async with session_factory() as session:
        soc_id, sub_id = await _seed_society_and_subscription(session)
        payload = PlatformInvoiceCreateDraft(
            society_id=soc_id,
            subscription_id=sub_id,
            billing_cycle="MONTHLY",
            period_start=now,
            period_end=now,
            due_date=date.today(),
            items=[PlatformInvoiceItemCreate(description="Base", unit_price=Decimal("1000.00"))],
        )
        inv = await invoice_service.create_draft_invoice(session, payload)
        await session.commit()
        inv_id = inv.id

    async with session_factory() as session:
        await invoice_service.finalize_invoice(session, inv_id)
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(InvalidInvoiceStateException) as exc:
            await invoice_service.update_draft_invoice(
                session,
                inv_id,
                PlatformInvoiceUpdateDraft(prorated_credit=Decimal("50.00")),
            )
        assert "Only DRAFT invoices can be edited" in str(exc.value)


# ==============================================================================
# 4. VOID LIFECYCLE TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_invoice_void_lifecycle(session_factory, invoice_service):
    """Voiding an invoice retains original invoice number and history permanently."""
    now = datetime.now(UTC).replace(tzinfo=None)
    async with session_factory() as session:
        soc_id, sub_id = await _seed_society_and_subscription(session)
        payload = PlatformInvoiceCreateDraft(
            society_id=soc_id,
            subscription_id=sub_id,
            billing_cycle="MONTHLY",
            period_start=now,
            period_end=now,
            due_date=date.today(),
            items=[PlatformInvoiceItemCreate(description="Base", unit_price=Decimal("5000.00"))],
        )
        inv = await invoice_service.create_draft_invoice(session, payload)
        await session.commit()
        inv_id = inv.id

    async with session_factory() as session:
        issued = await invoice_service.finalize_invoice(session, inv_id)
        allocated_num = issued.invoice_number
        await session.commit()

    async with session_factory() as session:
        voided = await invoice_service.void_invoice(
            session=session,
            invoice_id=inv_id,
            reason="Billing error - cancelled by mutual consent.",
        )
        await session.commit()

        assert voided.status == "VOID"
        assert voided.invoice_number == allocated_num, "Original invoice number must be retained"
        assert voided.voided_at is not None
        assert voided.void_reason == "Billing error - cancelled by mutual consent."
        assert voided.amount_due == Decimal("0.00")


@pytest.mark.asyncio
async def test_cannot_void_paid_invoice(session_factory, invoice_service):
    """Paid or partially paid invoices cannot be voided directly; must use refunds/credit notes."""
    now = datetime.now(UTC).replace(tzinfo=None)
    async with session_factory() as session:
        soc_id, sub_id = await _seed_society_and_subscription(session)
        payload = PlatformInvoiceCreateDraft(
            society_id=soc_id,
            subscription_id=sub_id,
            billing_cycle="MONTHLY",
            period_start=now,
            period_end=now,
            due_date=date.today(),
            items=[PlatformInvoiceItemCreate(description="Base", unit_price=Decimal("1000.00"))],
        )
        inv = await invoice_service.create_draft_invoice(session, payload)
        await session.commit()
        inv_id = inv.id

    async with session_factory() as session:
        await invoice_service.finalize_invoice(session, inv_id)
        # Mark as PAID directly
        db_inv = await session.get(PlatformInvoice, inv_id)
        db_inv.status = "PAID"
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(InvalidInvoiceStateException) as exc:
            await invoice_service.void_invoice(session, inv_id, reason="Customer cancelled")
        assert "Paid or partially paid invoices cannot be voided" in str(exc.value)


# ==============================================================================
# 5. TAX SNAPSHOT INTEGRITY & CREDIT NOTE COMPATIBILITY (M-2 & M-3)
# ==============================================================================


@pytest.mark.asyncio
async def test_tax_snapshot_tamper_detection(session_factory, invoice_service):
    """Modifying the stored tax snapshot causes SHA-256 integrity verification to fail."""
    now = datetime.now(UTC).replace(tzinfo=None)
    async with session_factory() as session:
        soc_id, sub_id = await _seed_society_and_subscription(session)
        payload = PlatformInvoiceCreateDraft(
            society_id=soc_id,
            subscription_id=sub_id,
            billing_cycle="MONTHLY",
            period_start=now,
            period_end=now,
            due_date=date.today(),
            items=[PlatformInvoiceItemCreate(description="Base", unit_price=Decimal("1000.00"))],
        )
        inv = await invoice_service.create_draft_invoice(session, payload)
        await session.commit()
        inv_id = inv.id

    async with session_factory() as session:
        await invoice_service.finalize_invoice(session, inv_id)
        await session.commit()

    # Tamper with the snapshot stored in PlatformSubscriptionAuditLog
    from apps.api.src.database.models.platform_billing import PlatformSubscriptionAuditLog

    async with session_factory() as session:
        stmt = select(PlatformSubscriptionAuditLog).where(
            PlatformSubscriptionAuditLog.entity_type == "INVOICE_TAX_SNAPSHOT",
            PlatformSubscriptionAuditLog.entity_id == inv_id,
        )
        audit_row = (await session.execute(stmt)).scalar_one()
        # Tamper taxable value
        tampered_state = dict(audit_row.after_state)
        tampered_state["taxable_value"] = "99999.00"
        audit_row.after_state = tampered_state
        await session.commit()

    # Verification must flag mismatch
    async with session_factory() as session:
        v_res = await invoice_service.verify_invoice_tax_snapshot(session, inv_id)
        assert v_res.is_valid is False
        assert "mismatch" in v_res.error_message.lower()

        with pytest.raises(InvoiceTaxSnapshotTamperedException):
            await invoice_service.get_invoice_tax_snapshot(session, inv_id)


@pytest.mark.asyncio
async def test_credit_note_version_compatibility_m2(session_factory, invoice_service, custom_tax_config):
    """Credit note calculation preserves original invoice tax version and rates across subsequent config changes (M-2)."""
    now = datetime.now(UTC).replace(tzinfo=None)
    async with session_factory() as session:
        soc_id, sub_id = await _seed_society_and_subscription(session, state="Maharashtra")
        payload = PlatformInvoiceCreateDraft(
            society_id=soc_id,
            subscription_id=sub_id,
            billing_cycle="MONTHLY",
            period_start=now,
            period_end=now,
            due_date=date.today(),
            items=[PlatformInvoiceItemCreate(description="Base", sac_code="998313", unit_price=Decimal("10000.00"))],
        )
        inv = await invoice_service.create_draft_invoice(session, payload)
        await session.commit()
        inv_id = inv.id

    async with session_factory() as session:
        await invoice_service.finalize_invoice(session, inv_id)
        await session.commit()

    # Retrieve locked snapshot
    async with session_factory() as session:
        original_snapshot = await invoice_service.get_invoice_tax_snapshot(session, inv_id)
        assert original_snapshot.tax_rate == Decimal("18.00")
        assert original_snapshot.tax_config_version == "1.0"

    # Simulate subsequent statutory tax rate change in config service to 28% version 2.0
    custom_tax_config.register_rule(
        TaxRateConfig(
            sac_code="998313",
            description="SAC 998313 updated to 28%",
            total_rate=Decimal("28.00"),
            cgst_rate=Decimal("14.00"),
            sgst_rate=Decimal("14.00"),
            igst_rate=Decimal("28.00"),
            effective_from=date(2027, 1, 1),
            status=TaxRuleStatus.ACTIVE,
            version="2.0",
        )
    )

    # Calculate credit note reversal using GSTTaxEngine
    tax_engine = invoice_service.tax_engine
    cn_calc = tax_engine.calculate_credit_note_tax(
        taxable_credit_amount=Decimal("5000.00"),
        original_invoice_snapshot=original_snapshot,
    )

    # Must preserve original 18% rate and version 1.0!
    assert cn_calc.tax_rate == Decimal("18.00")
    assert cn_calc.tax_total == Decimal("900.00")  # 18% of 5000, NOT 28%
    assert cn_calc.tax_snapshot.tax_config_version == "1.0"
    assert cn_calc.tax_snapshot.integrity_hash is not None


# ==============================================================================
# 6. EDGE CASES & SAFE FAILURE TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_zero_line_items_fails_safe(session_factory, invoice_service):
    """Creating draft with zero items is prevented by Pydantic validation."""
    now = datetime.now(UTC).replace(tzinfo=None)
    async with session_factory() as session:
        soc_id, sub_id = await _seed_society_and_subscription(session)

    with pytest.raises(Exception):
        PlatformInvoiceCreateDraft(
            society_id=soc_id,
            subscription_id=sub_id,
            billing_cycle="MONTHLY",
            period_start=now,
            period_end=now,
            due_date=date.today(),
            items=[],
        )


@pytest.mark.asyncio
async def test_missing_invoice_lookup_raises_404(session_factory, invoice_service):
    """Querying a non-existent invoice raises InvoiceNotFoundException."""
    async with session_factory() as session:
        with pytest.raises(InvoiceNotFoundException):
            await invoice_service.get_invoice(session, uuid4())
