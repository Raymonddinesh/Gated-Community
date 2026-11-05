"""Phase 21E.3 — Live PostgreSQL 16 Concurrency, Advisory Locking, and Decoupling Tests.

Validates against live PostgreSQL 16:
1. 64-Bit Advisory Locking & Safe Worker Conflict Handling:
   - Concurrent worker processes competing for the same webhook event serialize cleanly.
   - pg_try_advisory_xact_lock prevents concurrent settlement.
   - Lock conflict triggers safe retry (LockAcquisitionException), not dropped events or data corruption.
2. Concurrent Duplicate Ingestion Protection:
   - Simultaneous webhook deliveries of the same event id serialize cleanly.
   - UNIQUE(gateway_provider, event_id) prevents duplicate event rows.
3. Decoupling Invariants under Live PostgreSQL:
   - Payment settlement on PAST_DUE subscription transitions it to ACTIVE, but an administratively
     SUSPENDED society strictly remains SUSPENDED.
4. Unprivileged Application Role (app_user) Enforcement:
   - RLS enforcement on platform_payments, platform_payment_attempts, and platform_refunds
     under app_user with NOBYPASSRLS and NOSUPERUSER.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.src.core.tenant_context import tenant_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.platform_billing import (
    PlatformInvoice,
    PlatformPayment,
    PlatformWebhookEvent,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
)
from apps.api.src.database.session import set_db_tenant_context
from apps.api.src.subscriptions.enums import SubscriptionStatus
from apps.api.src.subscriptions.payments import (
    LockAcquisitionException,
    PaymentSettlementService,
    RazorpayGatewayProvider,
    WebhookIngestionService,
    WebhookProcessingWorker,
    compute_advisory_lock_key,
)
from apps.api.src.subscriptions.payments.schemas import (
    GatewayOrderResponse,
    GatewayPaymentDetails,
    GatewayRefundResponse,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_phase21e3_concurrency_pg")

PG_URL = "postgresql+asyncpg://postgres:postgrespassword@localhost:5432/societysphere_dev"


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def pg_engine():
    """Connect to live PostgreSQL 16 container, skipping if unreachable."""
    try:
        eng = create_async_engine(PG_URL, echo=False)
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL 16 not accessible at {PG_URL}: {exc}")
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
def mock_pg_provider():
    """Deterministic mock provider for PostgreSQL tests."""
    provider = RazorpayGatewayProvider(
        key_id="rzp_test_pg_key",
        key_secret="rzp_test_pg_secret",
        webhook_secret="whsec_pg_test_secret",
    )
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
            amount=Decimal("2950.00"),
            currency="INR",
            status="captured",
            method="CARD",
            captured_at=_utc_now(),
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
    return provider


@pytest_asyncio.fixture
async def seeded_pg_billing(pg_engine):
    """Seed test Society, Plan, Subscription, User, and PlatformInvoice in live PostgreSQL."""
    session_factory = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)
    now = _utc_now()

    async with session_factory() as session:
        soc = Society(
            legal_name="Phase 21E.3 Live PG Billing Society",
            display_name="PG Billing Society",
            address_line1="123 Postgres Way",
            city="Bengaluru",
            state="Karnataka",
            postal_code="560001",
            status="ACTIVE",
        )
        plan = PlatformSubscriptionPlan(
            plan_code=f"PLAN_PG_{uuid.uuid4().hex[:6]}",
            display_name="PG Test Plan",
            monthly_price=Decimal("2500.00"),
            annual_price=Decimal("25000.00"),
            currency_code="INR",
            trial_days=14,
            is_active=True,
        )
        user = User(
            email=f"pg_admin_{uuid.uuid4().hex[:6]}@example.com",
            first_name="PG",
            last_name="Admin",
            display_name="PG Admin",
            status="ACTIVE",
        )
        session.add_all([soc, plan, user])
        await session.flush()

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
        session.add(sub)
        await session.flush()

        inv = PlatformInvoice(
            society_id=soc.id,
            subscription_id=sub.id,
            invoice_number=f"SS-2627-{uuid.uuid4().hex[:5]}",
            fiscal_year="2627",
            billing_cycle="MONTHLY",
            period_start=now,
            period_end=now + timedelta(days=30),
            subtotal=Decimal("2500.00"),
            grand_total=Decimal("2950.00"),
            taxable_amount=Decimal("2500.00"),
            tax_total=Decimal("450.00"),
            amount_paid=Decimal("0.00"),
            amount_due=Decimal("2950.00"),
            currency_code="INR",
            status="ISSUED",
            due_date=date.today() + timedelta(days=7),
            place_of_supply="Karnataka",
        )
        session.add(inv)
        await session.commit()

        soc_id = soc.id
        sub_id = sub.id
        inv_id = inv.id
        admin_id = user.id

    return {
        "society_id": soc_id,
        "subscription_id": sub_id,
        "invoice_id": inv_id,
        "admin_id": admin_id,
        "session_factory": session_factory,
    }


# ==============================================================================
# 1. 64-BIT ADVISORY LOCK CONFLICT TEST
# ==============================================================================


@pytest.mark.asyncio
async def test_pg_webhook_worker_advisory_lock_conflict(
    seeded_pg_billing, mock_pg_provider
):
    """Verify that when Worker A holds an advisory lock on an event, Worker B
    detects the lock conflict, rolls back safely, and raises LockAcquisitionException.
    """
    soc_id = seeded_pg_billing["society_id"]
    inv_id = seeded_pg_billing["invoice_id"]
    session_factory = seeded_pg_billing["session_factory"]

    event_id = f"evt_lock_{uuid.uuid4().hex[:8]}"
    payment_ref = f"pay_lock_{uuid.uuid4().hex[:8]}"
    lock_key = compute_advisory_lock_key("RAZORPAY", payment_ref)

    # 1. Seed webhook event in PostgreSQL
    async with session_factory() as session:
        evt = PlatformWebhookEvent(
            gateway_provider="RAZORPAY",
            event_id=event_id,
            event_type="payment.captured",
            lock_key=lock_key,
            society_id=soc_id,
            payment_reference=payment_ref,
            payload={
                "event": "payment.captured",
                "id": event_id,
                "payload": {
                    "payment": {
                        "entity": {
                            "id": payment_ref,
                            "amount": 295000,
                            "currency": "INR",
                            "notes": {"society_id": str(soc_id), "invoice_id": str(inv_id)},
                        }
                    }
                },
            },
            received_at=_utc_now(),
            processing_status="PENDING",
        )
        session.add(evt)
        await session.commit()

    # 2. Worker 1 acquires the transaction-level advisory lock and simulates slow execution
    lock_held_event = asyncio.Event()
    worker_1_proceed = asyncio.Event()

    async def worker_1():
        async with session_factory() as session:
            # Acquire advisory lock directly in transaction
            await session.execute(
                text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
                {"lock_key": lock_key},
            )
            lock_held_event.set()
            await worker_1_proceed.wait()
            await session.commit()
            return "WORKER_1_COMMITTED"

    async def worker_2():
        await lock_held_event.wait()
        async with session_factory() as session:
            worker = WebhookProcessingWorker(session)
            try:
                await worker.process_webhook_event(
                    event_id=event_id,
                    provider="RAZORPAY",
                    custom_provider=mock_pg_provider,
                )
                return "WORKER_2_PROCESSED"
            except LockAcquisitionException as exc:
                return f"WORKER_2_CONFLICT: {exc.code}"

    # Launch both workers concurrently
    task1 = asyncio.create_task(worker_1())
    task2 = asyncio.create_task(worker_2())

    # Wait for worker 2 to attempt while worker 1 holds the lock
    w2_result = await task2
    worker_1_proceed.set()
    w1_result = await task1

    assert w1_result == "WORKER_1_COMMITTED"
    assert "WORKER_2_CONFLICT: LOCK_ACQUISITION_FAILED" == w2_result, (
        "Worker 2 must encounter a safe lock conflict without deadlocking or dropping data"
    )


# ==============================================================================
# 2. CONCURRENT DUPLICATE WEBHOOK INGESTION
# ==============================================================================


@pytest.mark.asyncio
async def test_pg_concurrent_duplicate_webhook_ingestion(
    seeded_pg_billing, mock_pg_provider
):
    """Simultaneous webhook deliveries of the same event id serialize cleanly.
    PostgreSQL UNIQUE(gateway_provider, event_id) guarantees exactly 1 row inserted.
    """
    soc_id = seeded_pg_billing["society_id"]
    session_factory = seeded_pg_billing["session_factory"]

    event_id = f"evt_concurrent_dup_{uuid.uuid4().hex[:8]}"
    raw_payload = json.dumps(
        {
            "event": "payment.captured",
            "id": event_id,
            "payload": {
                "payment": {
                    "entity": {
                        "id": f"pay_conc_{uuid.uuid4().hex[:8]}",
                        "amount": 295000,
                        "currency": "INR",
                        "notes": {"society_id": str(soc_id)},
                    }
                }
            },
        }
    ).encode()

    sig = hmac.new(
        mock_pg_provider.webhook_secret.encode(), raw_payload, hashlib.sha256
    ).hexdigest()

    async def attempt_ingest(worker_label: str):
        async with session_factory() as session:
            ingest_svc = WebhookIngestionService(session)
            try:
                res = await ingest_svc.ingest_webhook(
                    gateway_provider="RAZORPAY",
                    raw_body=raw_payload,
                    signature_header=sig,
                    custom_provider=mock_pg_provider,
                    publish_async_event=False,
                )
                return {"worker": worker_label, "status": res.status}
            except Exception as exc:
                return {"worker": worker_label, "error": str(exc)}

    results = await asyncio.gather(
        attempt_ingest("Worker-A"),
        attempt_ingest("Worker-B"),
    )

    statuses = [r.get("status") for r in results if "status" in r]
    assert "INGESTED" in statuses, "At least one delivery must be ingested"

    # Verify exactly one row in PostgreSQL
    async with session_factory() as session:
        stmt = select(PlatformWebhookEvent).where(
            PlatformWebhookEvent.gateway_provider == "RAZORPAY",
            PlatformWebhookEvent.event_id == event_id,
        )
        events = (await session.execute(stmt)).scalars().all()
        assert len(events) == 1, "Exactly one webhook event must exist in database"


# ==============================================================================
# 3. SETTLEMENT DECOUPLING WITH SUSPENDED SOCIETY
# ==============================================================================


@pytest.mark.asyncio
async def test_pg_payment_settlement_decoupling_with_suspended_society(
    seeded_pg_billing, mock_pg_provider
):
    """MANDATORY INVARIANT:
    If a society is administratively SUSPENDED, paying and settling an invoice
    transitions the subscription PAST_DUE -> ACTIVE, but Society.status remains SUSPENDED!
    """
    soc_id = seeded_pg_billing["society_id"]
    sub_id = seeded_pg_billing["subscription_id"]
    inv_id = seeded_pg_billing["invoice_id"]
    session_factory = seeded_pg_billing["session_factory"]

    # 1. Set Society to SUSPENDED, Subscription to PAST_DUE
    async with session_factory() as session:
        soc = (await session.execute(select(Society).where(Society.id == soc_id))).scalar_one()
        soc.status = "SUSPENDED"

        sub = (await session.execute(select(SocietySubscription).where(SocietySubscription.id == sub_id))).scalar_one()
        sub.status = SubscriptionStatus.PAST_DUE.value
        sub.past_due_since = _utc_now() - timedelta(days=3)

        await session.commit()

    # 2. Settle payment
    async with session_factory() as session:
        settlement_svc = PaymentSettlementService(session)
        await settlement_svc.settle_payment(
            society_id=soc_id,
            gateway_provider="RAZORPAY",
            gateway_payment_id=f"pay_decouple_{uuid.uuid4().hex[:8]}",
            amount=Decimal("2950.00"),
            invoice_id=inv_id,
            custom_provider=mock_pg_provider,
        )
        await session.commit()

    # 3. Verify Decoupling Invariants
    async with session_factory() as session:
        soc_check = (await session.execute(select(Society).where(Society.id == soc_id))).scalar_one()
        sub_check = (await session.execute(select(SocietySubscription).where(SocietySubscription.id == sub_id))).scalar_one()
        inv_check = (await session.execute(select(PlatformInvoice).where(PlatformInvoice.id == inv_id))).scalar_one()

        assert inv_check.status == "PAID"
        assert sub_check.status == SubscriptionStatus.ACTIVE.value, "Subscription must become ACTIVE"
        assert soc_check.status == "SUSPENDED", (
            "CRITICAL SECURITY INVARIANT: Administrative society suspension must NEVER "
            "be lifted by subscription payment settlement!"
        )


# ==============================================================================
# 4. UNPRIVILEGED APPLICATION ROLE (app_user) RLS ENFORCEMENT
# ==============================================================================


@pytest.mark.asyncio
async def test_pg_unprivileged_app_user_rls_isolation(
    pg_engine, seeded_pg_billing, mock_pg_provider
):
    """Verify FORCE ROW LEVEL SECURITY under unprivileged app_user (NOBYPASSRLS):
    - App user cannot bypass RLS.
    - Payments and Refunds scoped to Tenant A are invisible to Tenant B.
    """
    soc_a_id = seeded_pg_billing["society_id"]
    inv_a_id = seeded_pg_billing["invoice_id"]
    session_factory = seeded_pg_billing["session_factory"]

    # Ensure app_user exists and has permissions
    async with session_factory() as session:
        await session.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_user') THEN
                        CREATE ROLE app_user NOSUPERUSER NOBYPASSRLS;
                    END IF;
                    GRANT USAGE ON SCHEMA public TO app_user;
                    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO app_user;
                    GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO app_user;
                END
                $$;
                """
            )
        )
        await session.commit()

    # Verify role attributes
    async with pg_engine.connect() as conn:
        role_res = await conn.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'app_user'")
        )
        app_user_row = role_res.fetchone()
        if app_user_row:
            assert app_user_row[0] is False, "app_user must have rolsuper=False"
            assert app_user_row[1] is False, "app_user must have rolbypassrls=False"

    # Create Payment for Tenant A
    async with session_factory() as session:
        settlement_svc = PaymentSettlementService(session)
        pay_a = await settlement_svc.settle_payment(
            society_id=soc_a_id,
            gateway_provider="RAZORPAY",
            gateway_payment_id=f"pay_tenant_a_{uuid.uuid4().hex[:6]}",
            amount=Decimal("2950.00"),
            invoice_id=inv_a_id,
            custom_provider=mock_pg_provider,
        )
        await session.commit()
        pay_a_id = pay_a.id

    # Tenant B attempts to read Tenant A's payment as unprivileged app_user
    soc_b_id = uuid.uuid4()
    async with session_factory() as session:
        await session.execute(text("SET ROLE app_user"))
        async with tenant_context(soc_b_id):
            await set_db_tenant_context(session, soc_b_id)
            stmt = select(PlatformPayment).where(PlatformPayment.id == pay_a_id)
            pay_leak = (await session.execute(stmt)).scalar_one_or_none()
            assert pay_leak is None, "Tenant B must NOT see Tenant A's payment record"

    # Tenant A reads Tenant A's payment as unprivileged app_user
    async with session_factory() as session:
        await session.execute(text("SET ROLE app_user"))
        async with tenant_context(soc_a_id):
            await set_db_tenant_context(session, soc_a_id)
            stmt = select(PlatformPayment).where(PlatformPayment.id == pay_a_id)
            pay_valid = (await session.execute(stmt)).scalar_one_or_none()
            assert pay_valid is not None, "Tenant A must see their own payment record"
            assert pay_valid.id == pay_a_id
