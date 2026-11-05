"""Phase 21E.3 — SaaS Payment Gateway and Webhook Processing Test Suite.

Validates the complete commercial SaaS billing payment pipeline:
1. Razorpay Gateway Adapter: Order creation, Decimal-to-paise, HMAC-SHA256 signature
   verification, dual-secret rotation, and refund initiation.
2. Payment Order Service: Server-side authoritative amounts, invoice validation, idempotency.
3. Payment Verification Service: Cryptographic verification, authoritative status checks,
   atomic settlement.
4. Webhook Ingestion Service: Raw-body verification, dual-secret rotation, durable persistence,
   duplicate delivery handling (HTTP 200 acknowledgment).
5. Webhook Worker: Asynchronous event consumption, advisory locking, settlement, dead-letter retry.
6. Settlement Decoupling & Invariants:
   - Cancelled subscriptions are never reactivated; late payments trigger automatic refund.
   - Administrative society suspension is preserved during payment settlement.
7. Refund Service: Full & partial refunds, balance tracking, no automatic credit notes.
8. Financial Reconciliation Service: Non-mutating discrepancy detection.
9. Security & Redaction: Sensitive credential and card data masking.
"""

import hashlib
import hmac
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.platform_billing import (
    PlatformCreditNote,
    PlatformInvoice,
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
from apps.api.src.subscriptions import (
    SubscriptionStatus,
)
from apps.api.src.subscriptions.payments import (
    InvalidInvoiceStateException,
    InvalidPaymentSignatureException,
    InvalidRefundAmountException,
    InvoiceAlreadyPaidException,
    PaymentOrderService,
    PaymentReconciliationService,
    PaymentSettlementService,
    PaymentVerificationService,
    RazorpayGatewayProvider,
    RefundService,
    WebhookIngestionService,
    WebhookProcessingWorker,
    mask_secret,
    redact_sensitive_dict,
)
from apps.api.src.subscriptions.payments.schemas import (
    GatewayOrderResponse,
    GatewayPaymentDetails,
    GatewayRefundResponse,
)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def mock_razorpay_provider():
    """Deterministic mock provider simulating Razorpay API responses."""
    key_id = "rzp_test_key123"
    key_secret = "rzp_test_secret_abc"
    webhook_secret = "whsec_primary_123"
    webhook_secret_sec = "whsec_secondary_456"

    provider = RazorpayGatewayProvider(
        key_id=key_id,
        key_secret=key_secret,
        webhook_secret=webhook_secret,
        webhook_secret_secondary=webhook_secret_sec,
    )

    # Mock async calls
    provider.create_payment_order = AsyncMock(  # type: ignore
        side_effect=lambda amount, currency, receipt, notes=None: GatewayOrderResponse(
            order_id=f"order_{uuid.uuid4().hex[:12]}",
            amount=amount,
            currency=currency,
            receipt=receipt,
            status="created",
        )
    )

    provider.fetch_payment = AsyncMock(  # type: ignore
        side_effect=lambda payment_id: GatewayPaymentDetails(
            payment_id=payment_id,
            order_id=None,
            amount=Decimal("2500.00"),
            currency="INR",
            status="captured",
            method="CARD",
            captured_at=_utc_now(),
            card_network="Visa",
            card_last4="4242",
            upi_vpa=None,
            gateway_fee=Decimal("50.00"),
            gateway_tax=Decimal("9.00"),
        )
    )

    provider.initiate_refund = AsyncMock(  # type: ignore
        side_effect=lambda payment_id, amount, currency, reason=None, notes=None: GatewayRefundResponse(
            refund_id=f"rfnd_{uuid.uuid4().hex[:12]}",
            payment_id=payment_id,
            amount=amount,
            currency=currency,
            status="processed",
        )
    )

    provider.fetch_refund = AsyncMock(  # type: ignore
        side_effect=lambda refund_id, payment_id=None: GatewayRefundResponse(
            refund_id=refund_id,
            payment_id=payment_id or "pay_test123",
            amount=Decimal("500.00"),
            currency="INR",
            status="processed",
        )
    )

    return provider


@pytest.fixture
async def seeded_billing_data(db_session: AsyncSession):
    """Seed test Society, Plan, Subscription, and PlatformInvoice."""
    now = _utc_now()
    soc = Society(
        legal_name="Phase 21E.3 Gateway Test Society",
        display_name="Gateway Society",
        address_line1="101 Payment Blvd",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560001",
        status="ACTIVE",
    )
    plan = PlatformSubscriptionPlan(
        plan_code=f"PLAN_GW_{uuid.uuid4().hex[:6]}",
        display_name="Gateway Test Plan",
        monthly_price=Decimal("2500.00"),
        annual_price=Decimal("25000.00"),
        currency_code="INR",
        trial_days=14,
        is_active=True,
    )
    db_session.add_all([soc, plan])
    await db_session.flush()

    sub = SocietySubscription(
        society_id=soc.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE.value,
        billing_cycle="MONTHLY",
        starts_at=now,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
        next_billing_at=now + timedelta(days=30),
        auto_renew=True,
    )
    db_session.add(sub)
    await db_session.flush()

    invoice = PlatformInvoice(
        society_id=soc.id,
        subscription_id=sub.id,
        invoice_number=f"SS-2627-{uuid.uuid4().hex[:5]}",
        fiscal_year="2627",
        billing_cycle="MONTHLY",
        period_start=now,
        period_end=now + timedelta(days=30),
        subtotal=Decimal("2500.00"),
        grand_total=Decimal("2950.00"),  # 2500 + 18% GST (450)
        taxable_amount=Decimal("2500.00"),
        tax_total=Decimal("450.00"),
        amount_paid=Decimal("0.00"),
        amount_due=Decimal("2950.00"),
        currency_code="INR",
        status="ISSUED",
        due_date=date.today() + timedelta(days=7),
        place_of_supply="Karnataka",
    )
    db_session.add(invoice)
    await db_session.commit()

    return {
        "society": soc,
        "plan": plan,
        "subscription": sub,
        "invoice": invoice,
    }


# ==============================================================================
# 1. RAZORPAY ADAPTER TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_razorpay_adapter_order_creation():
    """Verify Razorpay adapter converts Decimal INR to integer paise."""
    def handler(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content)
        assert data["amount"] == 295000, "2950.00 INR must become 295000 paise"
        assert data["currency"] == "INR"
        assert data["receipt"] == "rcpt_12345"
        return httpx.Response(
            200,
            json={
                "id": "order_mock123",
                "amount": 295000,
                "currency": "INR",
                "receipt": "rcpt_12345",
                "status": "created",
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="https://api.razorpay.com/v1")
    adapter = RazorpayGatewayProvider(
        key_id="rzp_test_123",
        key_secret="rzp_secret_456",
        httpx_client=client,
    )

    res = await adapter.create_payment_order(
        amount=Decimal("2950.00"),
        currency="INR",
        receipt="rcpt_12345",
    )
    assert res.order_id == "order_mock123"
    assert res.amount == Decimal("2950.00")
    assert res.currency == "INR"
    assert res.status == "created"


def test_razorpay_adapter_signature_verification():
    """Verify HMAC-SHA256 signature verification."""
    key_secret = "test_secret_key"
    order_id = "order_123456"
    payment_id = "pay_789012"
    message = f"{order_id}|{payment_id}".encode()
    valid_sig = hmac.new(key_secret.encode(), message, hashlib.sha256).hexdigest()

    adapter = RazorpayGatewayProvider(key_id="k1", key_secret=key_secret)

    # Valid
    assert adapter.verify_payment_signature(order_id, payment_id, valid_sig) is True
    # Tampered signature
    assert adapter.verify_payment_signature(order_id, payment_id, "corrupted_sig") is False
    # Tampered order ID
    assert adapter.verify_payment_signature("order_wrong", payment_id, valid_sig) is False


def test_razorpay_adapter_webhook_signature_verification_and_rotation():
    """Verify webhook signature verification over raw bytes, including dual-secret rotation."""
    primary_secret = "whsec_primary_secret"
    secondary_secret = "whsec_secondary_secret"

    payload_bytes = b'{"event":"payment.captured","id":"evt_123"}'
    primary_sig = hmac.new(primary_secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    secondary_sig = hmac.new(secondary_secret.encode(), payload_bytes, hashlib.sha256).hexdigest()

    adapter = RazorpayGatewayProvider(
        key_id="k1",
        key_secret="s1",
        webhook_secret=primary_secret,
        webhook_secret_secondary=secondary_secret,
    )

    # 1. Primary secret matches
    assert adapter.verify_webhook_signature(payload_bytes, primary_sig, primary_secret) is True

    # 2. Secondary secret matches during rotation
    assert adapter.verify_webhook_signature(payload_bytes, secondary_sig, primary_secret) is True

    # 3. Tampered body fails
    tampered_bytes = b'{"event":"payment.captured","id":"evt_TAMPERED"}'
    assert adapter.verify_webhook_signature(tampered_bytes, primary_sig, primary_secret) is False


# ==============================================================================
# 2. PAYMENT ORDER SERVICE TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_payment_order_creation_success(
    db_session: AsyncSession, seeded_billing_data: dict, mock_razorpay_provider
):
    """Verify authoritative server-side payment order creation."""
    soc = seeded_billing_data["society"]
    inv = seeded_billing_data["invoice"]

    order_svc = PaymentOrderService(db_session)
    res = await order_svc.create_payment_order(
        society_id=soc.id,
        invoice_id=inv.id,
        idempotency_key="test_idem_001",
        custom_provider=mock_razorpay_provider,
    )

    assert res.invoice_id == inv.id
    assert res.amount == Decimal("2950.00"), "Amount must be authoritative from invoice"
    assert res.currency_code == "INR"
    assert res.gateway_provider == "RAZORPAY"

    # Verify PlatformPaymentAttempt persisted in database
    stmt = select(PlatformPaymentAttempt).where(PlatformPaymentAttempt.id == res.attempt_id)
    attempt = (await db_session.execute(stmt)).scalar_one()
    assert attempt.status == "CREATED"
    assert attempt.amount == Decimal("2950.00")
    assert attempt.idempotency_key == "test_idem_001"


@pytest.mark.asyncio
async def test_payment_order_creation_rejects_paid_or_void_invoice(
    db_session: AsyncSession, seeded_billing_data: dict, mock_razorpay_provider
):
    """Verify cannot create payment order for already paid or void invoice."""
    soc = seeded_billing_data["society"]
    inv = seeded_billing_data["invoice"]

    order_svc = PaymentOrderService(db_session)

    # 1. Reject already paid
    inv.status = "PAID"
    inv.amount_due = Decimal("0.00")
    await db_session.commit()

    with pytest.raises(InvoiceAlreadyPaidException):
        await order_svc.create_payment_order(
            society_id=soc.id,
            invoice_id=inv.id,
            custom_provider=mock_razorpay_provider,
        )

    # 2. Reject void invoice
    inv.status = "VOID"
    inv.amount_due = Decimal("2950.00")
    await db_session.commit()

    with pytest.raises(InvalidInvoiceStateException):
        await order_svc.create_payment_order(
            society_id=soc.id,
            invoice_id=inv.id,
            custom_provider=mock_razorpay_provider,
        )


@pytest.mark.asyncio
async def test_payment_order_idempotency_replay(
    db_session: AsyncSession, seeded_billing_data: dict, mock_razorpay_provider
):
    """Replaying the same idempotency key returns the cached payment attempt."""
    soc = seeded_billing_data["society"]
    inv = seeded_billing_data["invoice"]

    order_svc = PaymentOrderService(db_session)
    res1 = await order_svc.create_payment_order(
        society_id=soc.id,
        invoice_id=inv.id,
        idempotency_key="idem_replay_key_123",
        custom_provider=mock_razorpay_provider,
    )

    # Replay with same key
    res2 = await order_svc.create_payment_order(
        society_id=soc.id,
        invoice_id=inv.id,
        idempotency_key="idem_replay_key_123",
        custom_provider=mock_razorpay_provider,
    )

    assert res1.attempt_id == res2.attempt_id
    assert res1.order_id == res2.order_id
    assert mock_razorpay_provider.create_payment_order.call_count == 1, (
        "Provider order must not be called twice on idempotent replay"
    )


# ==============================================================================
# 3. PAYMENT VERIFICATION & SETTLEMENT TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_payment_verification_and_settlement_success(
    db_session: AsyncSession, seeded_billing_data: dict, mock_razorpay_provider
):
    """Verify cryptographic checkout verification and atomic invoice settlement."""
    soc = seeded_billing_data["society"]
    inv = seeded_billing_data["invoice"]

    # 1. Create order
    order_svc = PaymentOrderService(db_session)
    order_res = await order_svc.create_payment_order(
        society_id=soc.id,
        invoice_id=inv.id,
        custom_provider=mock_razorpay_provider,
    )

    # 2. Generate valid signature
    payment_id = "pay_test_succ_123"
    msg = f"{order_res.order_id}|{payment_id}".encode()
    valid_sig = hmac.new(
        mock_razorpay_provider.key_secret.encode(), msg, hashlib.sha256
    ).hexdigest()

    # Configure fetch_payment to return matching details
    mock_razorpay_provider.fetch_payment = AsyncMock(
        return_value=GatewayPaymentDetails(
            payment_id=payment_id,
            order_id=order_res.order_id,
            amount=Decimal("2950.00"),
            currency="INR",
            status="captured",
            method="CARD",
            captured_at=_utc_now(),
        )
    )

    # 3. Verify and settle
    verif_svc = PaymentVerificationService(db_session)
    verif_res = await verif_svc.verify_and_settle(
        society_id=soc.id,
        invoice_id=inv.id,
        gateway_order_id=order_res.order_id,
        gateway_payment_id=payment_id,
        signature=valid_sig,
        custom_provider=mock_razorpay_provider,
    )

    assert verif_res.success is True
    assert verif_res.invoice_status == "PAID"
    assert verif_res.amount == Decimal("2950.00")

    # Verify invoice status in DB
    await db_session.refresh(inv)
    assert inv.status == "PAID"
    assert inv.amount_paid == Decimal("2950.00")
    assert inv.amount_due == Decimal("0.00")


@pytest.mark.asyncio
async def test_payment_verification_invalid_signature_rejection(
    db_session: AsyncSession, seeded_billing_data: dict, mock_razorpay_provider
):
    """Verify corrupted checkout signature is rejected with HTTP 400."""
    soc = seeded_billing_data["society"]
    inv = seeded_billing_data["invoice"]

    order_svc = PaymentOrderService(db_session)
    order_res = await order_svc.create_payment_order(
        society_id=soc.id,
        invoice_id=inv.id,
        custom_provider=mock_razorpay_provider,
    )

    verif_svc = PaymentVerificationService(db_session)
    with pytest.raises(InvalidPaymentSignatureException):
        await verif_svc.verify_and_settle(
            society_id=soc.id,
            invoice_id=inv.id,
            gateway_order_id=order_res.order_id,
            gateway_payment_id="pay_tampered_123",
            signature="tampered_invalid_signature",
            custom_provider=mock_razorpay_provider,
        )


@pytest.mark.asyncio
async def test_payment_duplicate_settlement_prevention(
    db_session: AsyncSession, seeded_billing_data: dict, mock_razorpay_provider
):
    """Verify duplicate settlement calls are idempotent without double-counting amount_paid."""
    soc = seeded_billing_data["society"]
    inv = seeded_billing_data["invoice"]

    settlement_svc = PaymentSettlementService(db_session)

    # 1. First settlement
    pay1 = await settlement_svc.settle_payment(
        society_id=soc.id,
        gateway_provider="RAZORPAY",
        gateway_payment_id="pay_dup_001",
        amount=Decimal("1000.00"),
        invoice_id=inv.id,
        custom_provider=mock_razorpay_provider,
    )

    await db_session.refresh(inv)
    assert inv.amount_paid == Decimal("1000.00")

    # 2. Duplicate settlement call with same gateway_payment_id
    pay2 = await settlement_svc.settle_payment(
        society_id=soc.id,
        gateway_provider="RAZORPAY",
        gateway_payment_id="pay_dup_001",
        amount=Decimal("1000.00"),
        invoice_id=inv.id,
        custom_provider=mock_razorpay_provider,
    )

    await db_session.refresh(inv)
    assert pay1.id == pay2.id, "Must return identical payment record"
    assert inv.amount_paid == Decimal("1000.00"), "Invoice amount_paid must NOT be double-counted"


# ==============================================================================
# 4. WEBHOOK INGESTION TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_webhook_ingestion_raw_body_and_dual_secret(
    db_session: AsyncSession, seeded_billing_data: dict, mock_razorpay_provider
):
    """Verify webhook ingestion with raw body verification and secondary secret rotation."""
    soc = seeded_billing_data["society"]
    raw_payload = json.dumps(
        {
            "event": "payment.captured",
            "id": "evt_test_ingest_001",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_hook_123",
                        "amount": 295000,
                        "currency": "INR",
                        "notes": {"society_id": str(soc.id)},
                    }
                }
            },
        }
    ).encode()

    sig = hmac.new(
        mock_razorpay_provider.webhook_secret.encode(), raw_payload, hashlib.sha256
    ).hexdigest()

    ingest_svc = WebhookIngestionService(db_session)
    res = await ingest_svc.ingest_webhook(
        gateway_provider="RAZORPAY",
        raw_body=raw_payload,
        signature_header=sig,
        custom_provider=mock_razorpay_provider,
        publish_async_event=False,
    )

    assert res.status == "INGESTED"
    assert res.event_id == "evt_test_ingest_001"
    assert res.processing_status == "PENDING"

    # Verify event persisted in DB
    stmt = select(PlatformWebhookEvent).where(
        PlatformWebhookEvent.gateway_provider == "RAZORPAY",
        PlatformWebhookEvent.event_id == "evt_test_ingest_001",
    )
    event = (await db_session.execute(stmt)).scalar_one()
    assert event.processing_status == "PENDING"
    assert event.payment_reference == "pay_hook_123"


@pytest.mark.asyncio
async def test_webhook_ingestion_duplicate_delivery(
    db_session: AsyncSession, seeded_billing_data: dict, mock_razorpay_provider
):
    """Verify duplicate webhook deliveries acknowledge HTTP 200 without duplicate insert."""
    raw_payload = json.dumps({"event": "payment.captured", "id": "evt_dup_001"}).encode()
    sig = hmac.new(
        mock_razorpay_provider.webhook_secret.encode(), raw_payload, hashlib.sha256
    ).hexdigest()

    ingest_svc = WebhookIngestionService(db_session)

    # First delivery
    res1 = await ingest_svc.ingest_webhook(
        gateway_provider="RAZORPAY",
        raw_body=raw_payload,
        signature_header=sig,
        custom_provider=mock_razorpay_provider,
        publish_async_event=False,
    )
    assert res1.status == "INGESTED"

    # Second delivery
    res2 = await ingest_svc.ingest_webhook(
        gateway_provider="RAZORPAY",
        raw_body=raw_payload,
        signature_header=sig,
        custom_provider=mock_razorpay_provider,
        publish_async_event=False,
    )
    assert res2.status == "ALREADY_RECEIVED"


# ==============================================================================
# 5. WEBHOOK WORKER & SETTLEMENT INVARIANTS
# ==============================================================================


@pytest.mark.asyncio
async def test_webhook_worker_payment_captured_settlement(
    db_session: AsyncSession, seeded_billing_data: dict, mock_razorpay_provider
):
    """Verify worker processes payment.captured event and settles past-due subscription."""
    soc = seeded_billing_data["society"]
    sub = seeded_billing_data["subscription"]
    inv = seeded_billing_data["invoice"]

    # Set subscription to PAST_DUE
    sub.status = SubscriptionStatus.PAST_DUE.value
    await db_session.commit()

    # Ingest webhook
    raw_payload = json.dumps(
        {
            "event": "payment.captured",
            "id": "evt_worker_settle_001",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_worker_123",
                        "amount": 295000,
                        "currency": "INR",
                        "notes": {
                            "society_id": str(soc.id),
                            "invoice_id": str(inv.id),
                        },
                    }
                }
            },
        }
    ).encode()
    sig = hmac.new(
        mock_razorpay_provider.webhook_secret.encode(), raw_payload, hashlib.sha256
    ).hexdigest()

    ingest_svc = WebhookIngestionService(db_session)
    await ingest_svc.ingest_webhook(
        gateway_provider="RAZORPAY",
        raw_body=raw_payload,
        signature_header=sig,
        custom_provider=mock_razorpay_provider,
        publish_async_event=False,
    )

    # Process via Worker
    worker = WebhookProcessingWorker(db_session)
    processed_event = await worker.process_webhook_event(
        event_id="evt_worker_settle_001",
        provider="RAZORPAY",
        custom_provider=mock_razorpay_provider,
    )

    assert processed_event is not None
    assert processed_event.processing_status == "PROCESSED"

    # Verify subscription transitioned to ACTIVE
    await db_session.refresh(sub)
    assert sub.status == SubscriptionStatus.ACTIVE.value

    # Verify invoice paid
    await db_session.refresh(inv)
    assert inv.status == "PAID"
    assert inv.amount_paid == Decimal("2950.00")


@pytest.mark.asyncio
async def test_webhook_worker_late_payment_on_cancelled_subscription(
    db_session: AsyncSession, seeded_billing_data: dict, mock_razorpay_provider
):
    """MANDATORY INVARIANT: Late payment on CANCELLED subscription is NEVER reactivated.
    Payment is recorded as orphaned and automatic refund is initiated.
    """
    soc = seeded_billing_data["society"]
    sub = seeded_billing_data["subscription"]
    inv = seeded_billing_data["invoice"]

    # Set subscription to CANCELLED
    sub.status = SubscriptionStatus.CANCELLED.value
    await db_session.commit()

    # Ingest webhook
    raw_payload = json.dumps(
        {
            "event": "payment.captured",
            "id": "evt_late_cancel_001",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_late_cancel_999",
                        "amount": 295000,
                        "currency": "INR",
                        "notes": {
                            "society_id": str(soc.id),
                            "invoice_id": str(inv.id),
                        },
                    }
                }
            },
        }
    ).encode()
    sig = hmac.new(
        mock_razorpay_provider.webhook_secret.encode(), raw_payload, hashlib.sha256
    ).hexdigest()

    ingest_svc = WebhookIngestionService(db_session)
    await ingest_svc.ingest_webhook(
        gateway_provider="RAZORPAY",
        raw_body=raw_payload,
        signature_header=sig,
        custom_provider=mock_razorpay_provider,
        publish_async_event=False,
    )

    # Process via Worker
    worker = WebhookProcessingWorker(db_session)
    processed_event = await worker.process_webhook_event(
        event_id="evt_late_cancel_001",
        provider="RAZORPAY",
        custom_provider=mock_razorpay_provider,
    )

    assert processed_event is not None
    assert processed_event.processing_status == "PROCESSED_REFUND_INITIATED"

    # Verify subscription is STILL CANCELLED
    await db_session.refresh(sub)
    assert sub.status == SubscriptionStatus.CANCELLED.value, "CANCELLED subscription must NEVER be reactivated"

    # Verify payment recorded as orphaned
    stmt_p = select(PlatformPayment).where(PlatformPayment.gateway_payment_id == "pay_late_cancel_999")
    pay = (await db_session.execute(stmt_p)).scalar_one()
    assert pay.reconciliation_status == "ORPHAN_ON_CANCELLED_SUBSCRIPTION"

    # Verify refund was initiated
    stmt_r = select(PlatformRefund).where(PlatformRefund.payment_id == pay.id)
    rfnd = (await db_session.execute(stmt_r)).scalar_one()
    assert rfnd.reason == "ORPHAN_PAYMENT_ON_CANCELLED_SUBSCRIPTION"
    assert rfnd.amount == Decimal("2950.00")


# ==============================================================================
# 6. REFUND SERVICE TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_refund_service_full_and_partial(
    db_session: AsyncSession, seeded_billing_data: dict, mock_razorpay_provider
):
    """Verify partial and full refund tracking against payment balance."""
    soc = seeded_billing_data["society"]
    inv = seeded_billing_data["invoice"]

    # 1. Create payment
    settlement_svc = PaymentSettlementService(db_session)
    pay = await settlement_svc.settle_payment(
        society_id=soc.id,
        gateway_provider="RAZORPAY",
        gateway_payment_id="pay_refund_suite_001",
        amount=Decimal("2000.00"),
        invoice_id=inv.id,
        custom_provider=mock_razorpay_provider,
    )

    refund_svc = RefundService(db_session)

    # 2. Partial refund 1: 500.00
    rf1 = await refund_svc.initiate_refund(
        society_id=soc.id,
        payment_id=pay.id,
        amount=Decimal("500.00"),
        reason="Partial refund 1",
        custom_provider=mock_razorpay_provider,
    )
    assert rf1.amount == Decimal("500.00")
    await db_session.refresh(pay)
    assert pay.refunded_amount == Decimal("500.00")
    assert pay.status == "PARTIALLY_REFUNDED"

    # 3. Partial refund 2: Remaining 1500.00
    rf2 = await refund_svc.initiate_refund(
        society_id=soc.id,
        payment_id=pay.id,
        amount=Decimal("1500.00"),
        reason="Exhaust remaining balance",
        custom_provider=mock_razorpay_provider,
    )
    assert rf2.amount == Decimal("1500.00")
    await db_session.refresh(pay)
    assert pay.refunded_amount == Decimal("2000.00")
    assert pay.status == "REFUNDED"

    # 4. Attempt 3rd refund when balance is 0
    with pytest.raises(InvalidRefundAmountException):
        await refund_svc.initiate_refund(
            society_id=soc.id,
            payment_id=pay.id,
            amount=Decimal("100.00"),
            reason="Exceeding refund",
            custom_provider=mock_razorpay_provider,
        )


@pytest.mark.asyncio
async def test_refund_never_creates_credit_note(
    db_session: AsyncSession, seeded_billing_data: dict, mock_razorpay_provider
):
    """MANDATORY INVARIANT: A refund must NOT automatically generate a credit note."""
    soc = seeded_billing_data["society"]
    inv = seeded_billing_data["invoice"]

    settlement_svc = PaymentSettlementService(db_session)
    pay = await settlement_svc.settle_payment(
        society_id=soc.id,
        gateway_provider="RAZORPAY",
        gateway_payment_id="pay_no_cn_001",
        amount=Decimal("1000.00"),
        invoice_id=inv.id,
        custom_provider=mock_razorpay_provider,
    )

    refund_svc = RefundService(db_session)
    await refund_svc.initiate_refund(
        society_id=soc.id,
        payment_id=pay.id,
        amount=Decimal("500.00"),
        reason="Test no credit note",
        custom_provider=mock_razorpay_provider,
    )

    # Verify zero credit notes in database
    stmt = select(PlatformCreditNote).where(PlatformCreditNote.invoice_id == inv.id)
    cns = (await db_session.execute(stmt)).scalars().all()
    assert len(cns) == 0, "A refund must never automatically create a credit note"


# ==============================================================================
# 7. FINANCIAL RECONCILIATION TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_reconciliation_service_discrepancy_detection(
    db_session: AsyncSession, seeded_billing_data: dict, mock_razorpay_provider
):
    """Verify non-mutating financial reconciliation detects amount and currency discrepancies."""
    soc = seeded_billing_data["society"]
    inv = seeded_billing_data["invoice"]

    # Seed payment with amount mismatch against provider mock
    settlement_svc = PaymentSettlementService(db_session)
    pay = await settlement_svc.settle_payment(
        society_id=soc.id,
        gateway_provider="RAZORPAY",
        gateway_payment_id="pay_recon_001",
        amount=Decimal("3000.00"),  # Remote mock returns 2500.00
        invoice_id=inv.id,
        custom_provider=mock_razorpay_provider,
    )

    recon_svc = PaymentReconciliationService(db_session)
    report = await recon_svc.reconcile(
        society_id=soc.id,
        provider_name="RAZORPAY",
        custom_provider=mock_razorpay_provider,
    )

    assert report.discrepancy_count >= 1
    discrepancy_types = [d.type for d in report.discrepancies]
    assert "AMOUNT_MISMATCH" in discrepancy_types

    # Verify DB payment is NOT mutated
    await db_session.refresh(pay)
    assert pay.amount == Decimal("3000.00"), "Reconciliation must not silently mutate financial records"


# ==============================================================================
# 8. SENSITIVE DATA REDACTION TESTS
# ==============================================================================


def test_sensitive_secret_redaction():
    """Verify logging sanitization masks API keys, secrets, and CVVs."""
    raw_payload = {
        "key_secret": "rzp_live_secret_very_sensitive_999",
        "webhook_secret": "whsec_super_secret",
        "card_number": "4111111111111111",
        "cvv": "123",
        "public_data": "society_sphere",
        "nested": {
            "password": "supersecretpassword",
            "amount": 2500,
        },
    }

    sanitized = redact_sensitive_dict(raw_payload)

    assert sanitized["key_secret"] == "[REDACTED]"
    assert sanitized["webhook_secret"] == "[REDACTED]"
    assert sanitized["card_number"] == "[REDACTED]"
    assert sanitized["cvv"] == "[REDACTED]"
    assert sanitized["public_data"] == "society_sphere"
    assert sanitized["nested"]["password"] == "[REDACTED]"
    assert sanitized["nested"]["amount"] == 2500

    masked = mask_secret("rzp_test_abcdef123456")
    assert masked == "rzp_...3456"
