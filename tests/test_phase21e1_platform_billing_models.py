"""Phase 21E.1 — Platform Billing Database Foundation Unit & Model Integrity Tests."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.platform_billing import (
    PlatformBillingAdjustment,
    PlatformCreditNote,
    PlatformInvoice,
    PlatformInvoiceItem,
    PlatformInvoiceSequence,
    PlatformPayment,
    PlatformPaymentAttempt,
    PlatformRefund,
    PlatformWebhookEvent,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture
async def seeded_entities(db_session: AsyncSession):
    """Seed test Society, Plan, and Subscription."""
    soc = Society(
        legal_name="Phase 21E Test Society",
        display_name="Phase 21E Society",
        address_line1="123 Billing Blvd",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560001",
    )
    plan = PlatformSubscriptionPlan(
        plan_code=f"PLAN_21E_{uuid.uuid4().hex[:6]}",
        display_name="Phase 21E Plan",
        monthly_price=Decimal("1999.00"),
        annual_price=Decimal("19990.00"),
        currency_code="INR",
        trial_days=14,
        is_active=True,
    )
    db_session.add_all([soc, plan])
    await db_session.flush()

    sub = SocietySubscription(
        society_id=soc.id,
        plan_id=plan.id,
        status="ACTIVE",
        billing_cycle="MONTHLY",
        auto_renew=True,
        gateway_customer_id="cust_test_123",
        gateway_subscription_id="sub_test_123",
        starts_at=_utc_now(),
        current_period_start=_utc_now(),
        current_period_end=_utc_now(),
        next_billing_at=_utc_now(),
    )
    db_session.add(sub)
    await db_session.commit()
    return soc, plan, sub


@pytest.mark.asyncio
async def test_society_subscription_billing_fields(db_session: AsyncSession, seeded_entities):
    """Verify augmented billing fields on SocietySubscription."""
    soc, plan, sub = seeded_entities
    stmt = select(SocietySubscription).where(SocietySubscription.id == sub.id)
    res = await db_session.execute(stmt)
    loaded = res.scalar_one()

    assert loaded.billing_cycle == "MONTHLY"
    assert loaded.auto_renew is True
    assert loaded.gateway_customer_id == "cust_test_123"
    assert loaded.gateway_subscription_id == "sub_test_123"
    assert loaded.next_billing_at is not None


@pytest.mark.asyncio
async def test_platform_invoice_and_items_lifecycle(db_session: AsyncSession, seeded_entities):
    """Verify PlatformInvoice and PlatformInvoiceItem relationships and monetary precision."""
    soc, plan, sub = seeded_entities

    inv = PlatformInvoice(
        society_id=soc.id,
        subscription_id=sub.id,
        invoice_number=f"SS-2627-{uuid.uuid4().hex[:5]}",
        fiscal_year="2627",
        billing_cycle="MONTHLY",
        period_start=_utc_now(),
        period_end=_utc_now(),
        subtotal=Decimal("1999.00"),
        discount_total=Decimal("0.00"),
        prorated_credit=Decimal("0.00"),
        taxable_amount=Decimal("1999.00"),
        cgst_amount=Decimal("179.91"),
        sgst_amount=Decimal("179.91"),
        igst_amount=Decimal("0.00"),
        tax_total=Decimal("359.82"),
        grand_total=Decimal("2358.82"),
        amount_due=Decimal("2358.82"),
        currency_code="INR",
        status="ISSUED",
        due_date=date.today(),
        issued_at=_utc_now(),
        place_of_supply="Karnataka",
    )
    db_session.add(inv)
    await db_session.flush()

    item = PlatformInvoiceItem(
        invoice_id=inv.id,
        society_id=soc.id,
        item_index=1,
        item_type="BASE_PLAN",
        description="Standard Tier Monthly Subscription",
        sac_code="998313",
        quantity=Decimal("1.0000"),
        unit_price=Decimal("1999.00"),
        discount_amount=Decimal("0.00"),
        taxable_amount=Decimal("1999.00"),
        tax_rate=Decimal("18.00"),
        tax_amount=Decimal("359.82"),
        total_amount=Decimal("2358.82"),
    )
    db_session.add(item)
    await db_session.commit()

    stmt = select(PlatformInvoice).where(PlatformInvoice.id == inv.id)
    res = await db_session.execute(stmt)
    loaded_inv = res.scalar_one()

    assert loaded_inv.grand_total == Decimal("2358.82")
    assert loaded_inv.amount_due == Decimal("2358.82")
    assert loaded_inv.status == "ISSUED"


@pytest.mark.asyncio
async def test_platform_payment_and_attempt(db_session: AsyncSession, seeded_entities):
    """Verify PlatformPaymentAttempt and PlatformPayment capture."""
    soc, plan, sub = seeded_entities

    inv = PlatformInvoice(
        society_id=soc.id,
        subscription_id=sub.id,
        period_start=_utc_now(),
        period_end=_utc_now(),
        grand_total=Decimal("1000.00"),
        amount_due=Decimal("1000.00"),
        due_date=date.today(),
        place_of_supply="Karnataka",
    )
    db_session.add(inv)
    await db_session.flush()

    order_id = f"order_{uuid.uuid4().hex[:10]}"
    attempt = PlatformPaymentAttempt(
        society_id=soc.id,
        invoice_id=inv.id,
        gateway_provider="RAZORPAY",
        gateway_order_id=order_id,
        amount=Decimal("1000.00"),
        status="CREATED",
    )
    db_session.add(attempt)
    await db_session.flush()

    payment_id = f"pay_{uuid.uuid4().hex[:10]}"
    payment = PlatformPayment(
        society_id=soc.id,
        invoice_id=inv.id,
        payment_attempt_id=attempt.id,
        gateway_provider="RAZORPAY",
        gateway_payment_id=payment_id,
        payment_method="UPI",
        amount=Decimal("1000.00"),
        status="CAPTURED",
        reconciliation_status="RECONCILED",
        captured_at=_utc_now(),
    )
    db_session.add(payment)
    await db_session.commit()

    stmt = select(PlatformPayment).where(PlatformPayment.id == payment.id)
    res = await db_session.execute(stmt)
    loaded_pmt = res.scalar_one()

    assert loaded_pmt.gateway_payment_id == payment_id
    assert loaded_pmt.amount == Decimal("1000.00")
    assert loaded_pmt.status == "CAPTURED"


@pytest.mark.asyncio
async def test_platform_refund_integrity(db_session: AsyncSession, seeded_entities):
    """Verify PlatformRefund links cleanly to payment."""
    soc, plan, sub = seeded_entities

    payment = PlatformPayment(
        society_id=soc.id,
        gateway_provider="STRIPE",
        gateway_payment_id=f"ch_{uuid.uuid4().hex[:10]}",
        payment_method="CARD",
        amount=Decimal("2000.00"),
        captured_at=_utc_now(),
        reconciliation_status="ORPHAN_ON_CANCELLED_SUBSCRIPTION",
    )
    db_session.add(payment)
    await db_session.flush()

    rfnd_id = f"rfnd_{uuid.uuid4().hex[:10]}"
    refund = PlatformRefund(
        society_id=soc.id,
        payment_id=payment.id,
        gateway_provider="STRIPE",
        gateway_refund_id=rfnd_id,
        amount=Decimal("2000.00"),
        reason="ORPHAN_PAYMENT_ON_CANCELLED_SUBSCRIPTION",
        status="COMPLETED",
        initiated_by="SYSTEM",
        processed_at=_utc_now(),
    )
    payment.status = "REFUNDED"
    payment.refunded_amount = Decimal("2000.00")
    db_session.add(refund)
    await db_session.commit()

    stmt = select(PlatformRefund).where(PlatformRefund.id == refund.id)
    res = await db_session.execute(stmt)
    loaded_refund = res.scalar_one()

    assert loaded_refund.gateway_refund_id == rfnd_id
    assert loaded_refund.amount == Decimal("2000.00")
    assert loaded_refund.status == "COMPLETED"


@pytest.mark.asyncio
async def test_platform_webhook_event_idempotency_constraint(db_session: AsyncSession):
    """Verify unique constraint on (gateway_provider, event_id)."""
    event_id = f"evt_{uuid.uuid4().hex}"
    evt1 = PlatformWebhookEvent(
        gateway_provider="RAZORPAY",
        event_id=event_id,
        event_type="payment.captured",
        lock_key=123456789,
        payload={"id": event_id, "entity": "event"},
        processing_status="PENDING",
    )
    db_session.add(evt1)
    await db_session.commit()

    evt2 = PlatformWebhookEvent(
        gateway_provider="RAZORPAY",
        event_id=event_id,
        event_type="payment.captured",
        lock_key=123456789,
        payload={"id": event_id, "entity": "duplicate"},
        processing_status="PENDING",
    )
    db_session.add(evt2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_platform_invoice_sequences_model(db_session: AsyncSession):
    """Verify PlatformInvoiceSequence model."""
    fy = f"FY{uuid.uuid4().hex[:4]}"
    seq = PlatformInvoiceSequence(
        fiscal_year=fy,
        current_sequence=42,
    )
    db_session.add(seq)
    await db_session.commit()

    stmt = select(PlatformInvoiceSequence).where(PlatformInvoiceSequence.fiscal_year == fy)
    res = await db_session.execute(stmt)
    loaded_seq = res.scalar_one()
    assert loaded_seq.current_sequence == 42


@pytest.mark.asyncio
async def test_platform_credit_note_and_adjustment(db_session: AsyncSession, seeded_entities):
    """Verify PlatformCreditNote and PlatformBillingAdjustment models."""
    soc, plan, sub = seeded_entities

    inv = PlatformInvoice(
        society_id=soc.id,
        subscription_id=sub.id,
        period_start=_utc_now(),
        period_end=_utc_now(),
        grand_total=Decimal("5000.00"),
        amount_due=Decimal("5000.00"),
        due_date=date.today(),
        place_of_supply="Karnataka",
    )
    db_session.add(inv)
    await db_session.flush()

    cn_num = f"CN-2627-{uuid.uuid4().hex[:5]}"
    cn = PlatformCreditNote(
        society_id=soc.id,
        invoice_id=inv.id,
        credit_note_number=cn_num,
        fiscal_year="2627",
        taxable_amount=Decimal("1000.00"),
        tax_total=Decimal("180.00"),
        grand_total=Decimal("1180.00"),
        reason="DOWNGRADE_PRORATION",
        issued_at=_utc_now(),
    )
    db_session.add(cn)
    await db_session.flush()

    adj_key = f"PRORATE:{uuid.uuid4().hex}"
    adj = PlatformBillingAdjustment(
        society_id=soc.id,
        invoice_id=inv.id,
        credit_note_id=cn.id,
        adjustment_type="PRORATION_CREDIT",
        amount=Decimal("-1180.00"),
        idempotency_key=adj_key,
        reason="Proration downgrade credit",
    )
    db_session.add(adj)
    await db_session.commit()

    stmt = select(PlatformBillingAdjustment).where(PlatformBillingAdjustment.id == adj.id)
    res = await db_session.execute(stmt)
    loaded_adj = res.scalar_one()
    assert loaded_adj.amount == Decimal("-1180.00")
    assert loaded_adj.idempotency_key == adj_key
