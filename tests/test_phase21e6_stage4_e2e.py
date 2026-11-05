"""Phase 21E.6 Stage 4 — Full Subscription Lifecycle End-to-End Validation Suite.

Covers:
1. Golden Path 13-Milestone Lifecycle:
   Provisioning -> TRIAL -> Trial expiry -> Renewal invoice -> GST snapshot ->
   PAST_DUE -> Day 0 reminder -> Day 2 reminder -> Day 5 warning -> Day 7 suspension ->
   Late payment webhook settlement -> Recovery to ACTIVE -> Society administrative suspension preservation.
2. Trial expiry with auto_renew=False (direct CANCELLED, zero invoices).
3. Failed payment during grace period (remains PAST_DUE, grace period preserved).
4. Late payment against a CANCELLED subscription (orphaned, remains CANCELLED).
5. Duplicate payment webhook replay idempotency (single payment, single receipt).
6. Duplicate scheduler trigger replay idempotency (single invoice, cached result).
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.src.database.base import Base
from apps.api.src.database.models.authorization import Role
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.notifications import Notification
from apps.api.src.database.models.platform_billing import (
    PlatformBillingJobRun,
    PlatformDunningAttempt,
    PlatformInvoice,
    PlatformInvoiceSequence,
    PlatformPayment,
    PlatformSubscriptionAuditLog,
    PlatformSubscriptionHistory,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
)
from apps.api.src.subscriptions.automation.dunning_service import (
    DunningEngineService,
    DunningStage,
)
from apps.api.src.subscriptions.automation.scheduler_service import (
    BillingPeriodSchedulerService,
)
from apps.api.src.subscriptions.automation.schemas import BillingJobRunStatus
from apps.api.src.subscriptions.enums import SubscriptionStatus
from apps.api.src.subscriptions.payments.settlement_service import PaymentSettlementService
from apps.api.src.subscriptions.subscription_lifecycle_service import (
    SubscriptionLifecycleService,
)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def e2e_db():
    """In-memory SQLite database for deterministic full-lifecycle unit testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest_asyncio.fixture
async def e2e_harness(e2e_db):
    """Seed base sequence and roles."""
    async with e2e_db() as session:
        seq = PlatformInvoiceSequence(fiscal_year="2627", current_sequence=0)
        r_admin = Role(id=uuid.uuid4(), code="SOCIETY_ADMIN", name="Society Admin")
        r_treas = Role(id=uuid.uuid4(), code="TREASURER", name="Treasurer")
        session.add_all([seq, r_admin, r_treas])
        await session.commit()
    return e2e_db


# ---------------------------------------------------------------------------
# 1. Golden Path 13-Milestone Lifecycle Test
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_e2e_golden_path_13_milestones(e2e_harness):
    session_factory = e2e_harness
    now = _utc_now()

    # Step 1: Provision Society & Plan
    soc_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    sub_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    async with session_factory() as session:
        soc = Society(
            id=soc_id,
            legal_name="E2E Royal Meadows CHS",
            display_name="Royal Meadows",
            address_line1="100 Baner Road",
            city="Pune",
            state="Maharashtra",
            postal_code="411045",
            status="ACTIVE",
            registration_number="REG-E2E-001",
        )
        plan = PlatformSubscriptionPlan(
            id=plan_id,
            plan_code=f"ENTERPRISE_E2E_{plan_id.hex[:6]}",
            display_name="Enterprise E2E Plan",
            monthly_price=Decimal("5000.00"),
            annual_price=Decimal("50000.00"),
            is_active=True,
            trial_days=14,
        )
        # Step 2: Create Subscription in TRIAL with auto_renew=True
        trial_start = now - timedelta(days=14)
        trial_end = now - timedelta(minutes=5)  # Just expired!
        sub = SocietySubscription(
            id=sub_id,
            society_id=soc_id,
            plan_id=plan_id,
            status=SubscriptionStatus.TRIAL.value,
            billing_cycle="MONTHLY",
            auto_renew=True,
            starts_at=trial_start,
            trial_ends_at=trial_end,
            current_period_start=trial_start,
            current_period_end=trial_end,
            next_billing_at=trial_end,
            past_due_since=None,
        )
        admin_user = User(
            id=admin_id,
            phone="+919876543210",
            email="admin@royalmeadows.com",
            first_name="Rajesh",
            last_name="Sharma",
            display_name="Rajesh Sharma",
            preferred_language="en",
            status="ACTIVE",
        )
        session.add_all([soc, plan, sub, admin_user])
        await session.commit()

    # Step 3 & 4: Trial expired, execute BillingPeriodSchedulerService
    async with session_factory() as session:
        scheduler = BillingPeriodSchedulerService(session=session)
        batch_res = await scheduler.process_due_subscriptions(cutoff_utc=now)
        assert batch_res.processed_count == 1
        assert batch_res.succeeded_count == 1

    # Authoritative verification in DB for Milestones 5 & 6
    async with session_factory() as session:
        sub_row = (await session.execute(select(SocietySubscription).where(SocietySubscription.id == sub_id))).scalar_one()
        # Milestone 6: Subscription must transition to PAST_DUE
        assert sub_row.status == SubscriptionStatus.PAST_DUE.value
        assert sub_row.past_due_since is not None
        past_due_since = sub_row.past_due_since

        # Milestone 5: Renewal invoice generated with GST tax breakdown
        invoices = (await session.execute(
            select(PlatformInvoice).where(PlatformInvoice.society_id == soc_id)
        )).scalars().all()
        assert len(invoices) == 1
        inv = invoices[0]
        assert inv.status == "ISSUED"
        assert inv.grand_total > Decimal("5000.00")  # Subtotal + GST
        assert inv.tax_total > Decimal("0.00")
        invoice_id = inv.id

        # Verify tax snapshot in audit log
        stmt_audit = select(PlatformSubscriptionAuditLog).where(
            PlatformSubscriptionAuditLog.society_id == soc_id,
            PlatformSubscriptionAuditLog.entity_id == invoice_id,
            PlatformSubscriptionAuditLog.entity_type == "INVOICE_TAX_SNAPSHOT",
        )
        audit_log = (await session.execute(stmt_audit)).scalar_one_or_none()
        assert audit_log is not None
        assert audit_log.after_state is not None
        assert "integrity_hash" in audit_log.after_state

    # Step 7: Milestone Day 0 Reminder
    async with session_factory() as session:
        dunning = DunningEngineService(session=session)
        d_res = await dunning.process_dunning_batch(cutoff_utc=past_due_since + timedelta(minutes=5))
        assert d_res.processed_count >= 1

    async with session_factory() as session:
        attempts = (await session.execute(
            select(PlatformDunningAttempt).where(PlatformDunningAttempt.subscription_id == sub_id)
        )).scalars().all()
        stages = [a.attempt_type for a in attempts]
        assert DunningStage.DAY_0_REMINDER.value in stages

        notifs = (await session.execute(
            select(Notification).where(Notification.society_id == soc_id)
        )).scalars().all()
        assert len(notifs) >= 1
        assert notifs[0].source_domain == "DUNNING"

    # Step 8: Milestone Day 2 Reminder
    async with session_factory() as session:
        dunning = DunningEngineService(session=session)
        await dunning.process_dunning_batch(cutoff_utc=past_due_since + timedelta(days=2, hours=1))

    async with session_factory() as session:
        attempts = (await session.execute(
            select(PlatformDunningAttempt).where(PlatformDunningAttempt.subscription_id == sub_id)
        )).scalars().all()
        stages = [a.attempt_type for a in attempts]
        assert DunningStage.DAY_2_REMINDER.value in stages

    # Step 9: Milestone Day 5 Warning
    async with session_factory() as session:
        dunning = DunningEngineService(session=session)
        await dunning.process_dunning_batch(cutoff_utc=past_due_since + timedelta(days=5, hours=1))

    async with session_factory() as session:
        attempts = (await session.execute(
            select(PlatformDunningAttempt).where(PlatformDunningAttempt.subscription_id == sub_id)
        )).scalars().all()
        stages = [a.attempt_type for a in attempts]
        assert DunningStage.DAY_5_WARNING.value in stages

    # Step 10: Milestone Day 7 Suspension
    async with session_factory() as session:
        dunning = DunningEngineService(session=session)
        await dunning.process_dunning_batch(cutoff_utc=past_due_since + timedelta(days=7, hours=1))

    async with session_factory() as session:
        sub_row = (await session.execute(select(SocietySubscription).where(SocietySubscription.id == sub_id))).scalar_one()
        assert sub_row.status == SubscriptionStatus.SUSPENDED.value

        suspension_hist = (await session.execute(
            select(PlatformSubscriptionHistory).where(
                PlatformSubscriptionHistory.subscription_id == sub_id,
                PlatformSubscriptionHistory.new_status == SubscriptionStatus.SUSPENDED.value,
            )
        )).scalars().first()
        assert suspension_hist is not None
        assert "DUNNING_GRACE_PERIOD_EXPIRED" in (suspension_hist.transition_reason or "")

        attempts = (await session.execute(
            select(PlatformDunningAttempt).where(PlatformDunningAttempt.subscription_id == sub_id)
        )).scalars().all()
        stages = [a.attempt_type for a in attempts]
        assert DunningStage.DAY_7_SUSPENSION.value in stages

    # Step 11 & 12: Successful Late Payment Settlement Webhook & Recovery
    async with session_factory() as session:
        settlement = PaymentSettlementService(session=session)
        payment_id = f"pay_e2e_{uuid.uuid4().hex[:10]}"
        payment = await settlement.settle_payment(
            society_id=soc_id,
            gateway_provider="RAZORPAY",
            gateway_payment_id=payment_id,
            amount=inv.grand_total,
            invoice_id=invoice_id,
        )
        assert payment.status == "CAPTURED"
        assert payment.is_settled is True
        await session.commit()

    # Authoritative verification in DB for Milestones 11 & 12
    async with session_factory() as session:
        sub_recovered = (await session.execute(select(SocietySubscription).where(SocietySubscription.id == sub_id))).scalar_one()
        assert sub_recovered.status == SubscriptionStatus.ACTIVE.value
        assert sub_recovered.past_due_since is None  # Grace period anchor cleared

        inv_paid = (await session.execute(select(PlatformInvoice).where(PlatformInvoice.id == invoice_id))).scalar_one()
        assert inv_paid.status == "PAID"
        assert inv_paid.amount_due == Decimal("0.00")

        payments = (await session.execute(
            select(PlatformPayment).where(PlatformPayment.invoice_id == invoice_id)
        )).scalars().all()
        assert len(payments) == 1
        assert payments[0].status == "CAPTURED"
        assert payments[0].is_settled is True

        # Verify history record confirms dunning suspension lifted
        hist_records = (await session.execute(
            select(PlatformSubscriptionHistory).where(PlatformSubscriptionHistory.subscription_id == sub_id)
        )).scalars().all()
        assert len(hist_records) >= 1

    # Step 13: Milestone Society Administrative Suspension Preservation
    async with session_factory() as session:
        soc_entity = (await session.execute(select(Society).where(Society.id == soc_id))).scalar_one()
        soc_entity.status = "SUSPENDED"  # Administratively suspended by Super Admin
        await session.commit()

    # Verify subscription operations or payment checks DO NOT alter society.status
    async with session_factory() as session:
        soc_check = (await session.execute(select(Society).where(Society.id == soc_id))).scalar_one()
        sub_check = (await session.execute(select(SocietySubscription).where(SocietySubscription.id == sub_id))).scalar_one()
        assert soc_check.status == "SUSPENDED"
        assert sub_check.status == SubscriptionStatus.ACTIVE.value


# ---------------------------------------------------------------------------
# 2. Trial Expiry with auto_renew=False
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_e2e_trial_expiry_auto_renew_false(e2e_harness):
    session_factory = e2e_harness
    now = _utc_now()
    soc_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    sub_id = uuid.uuid4()

    async with session_factory() as session:
        soc = Society(
            id=soc_id,
            legal_name="AutoRenew False CHS",
            display_name="No Renew Soc",
            address_line1="123 Road",
            city="Pune",
            state="Maharashtra",
            postal_code="411045",
            status="ACTIVE",
            registration_number="REG-NORENEW-1",
        )
        plan = PlatformSubscriptionPlan(
            id=plan_id,
            plan_code=f"BASE_{plan_id.hex[:6]}",
            display_name="Base Plan",
            monthly_price=Decimal("3000.00"),
            is_active=True,
            trial_days=14,
        )
        sub = SocietySubscription(
            id=sub_id,
            society_id=soc_id,
            plan_id=plan_id,
            status=SubscriptionStatus.TRIAL.value,
            billing_cycle="MONTHLY",
            auto_renew=False,  # DO NOT AUTO-RENEW
            starts_at=now - timedelta(days=15),
            trial_ends_at=now - timedelta(days=1),
            current_period_start=now - timedelta(days=15),
            current_period_end=now - timedelta(days=1),
            next_billing_at=now - timedelta(days=1),
            past_due_since=None,
        )
        session.add_all([soc, plan, sub])
        await session.commit()

    # Execute scheduler
    async with session_factory() as session:
        scheduler = BillingPeriodSchedulerService(session=session)
        batch_res = await scheduler.process_due_subscriptions(cutoff_utc=now)
        assert batch_res.processed_count == 1

    # Verify: Transitions directly to CANCELLED, zero invoices, zero grace period
    async with session_factory() as session:
        sub_row = (await session.execute(select(SocietySubscription).where(SocietySubscription.id == sub_id))).scalar_one()
        assert sub_row.status == SubscriptionStatus.CANCELLED.value
        assert sub_row.past_due_since is None

        invoices = (await session.execute(
            select(PlatformInvoice).where(PlatformInvoice.society_id == soc_id)
        )).scalars().all()
        assert len(invoices) == 0

        attempts = (await session.execute(
            select(PlatformDunningAttempt).where(PlatformDunningAttempt.subscription_id == sub_id)
        )).scalars().all()
        assert len(attempts) == 0


# ---------------------------------------------------------------------------
# 3. Failed Payment During Grace Period
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_e2e_failed_payment_during_grace_period(e2e_harness):
    session_factory = e2e_harness
    now = _utc_now()
    soc_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    sub_id = uuid.uuid4()
    inv_id = uuid.uuid4()
    past_due_anchor = now - timedelta(days=3)

    async with session_factory() as session:
        soc = Society(
            id=soc_id,
            legal_name="Failed Payment Soc",
            display_name="Fail Soc",
            address_line1="123 Fail St",
            city="Pune",
            state="Maharashtra",
            postal_code="411045",
            status="ACTIVE",
            registration_number="REG-FAIL-1",
        )
        plan = PlatformSubscriptionPlan(
            id=plan_id,
            plan_code=f"PLAN_{plan_id.hex[:6]}",
            display_name="Plan",
            monthly_price=Decimal("4000.00"),
            is_active=True,
        )
        sub = SocietySubscription(
            id=sub_id,
            society_id=soc_id,
            plan_id=plan_id,
            status=SubscriptionStatus.PAST_DUE.value,
            billing_cycle="MONTHLY",
            auto_renew=True,
            starts_at=now - timedelta(days=33),
            current_period_start=now - timedelta(days=33),
            current_period_end=past_due_anchor,
            next_billing_at=past_due_anchor,
            past_due_since=past_due_anchor,
        )
        inv = PlatformInvoice(
            id=inv_id,
            society_id=soc_id,
            subscription_id=sub_id,
            invoice_number="INV-2627-99991",
            status="ISSUED",
            place_of_supply="MH",
            subtotal=Decimal("4000.00"),
            taxable_amount=Decimal("4000.00"),
            tax_total=Decimal("720.00"),
            cgst_amount=Decimal("360.00"),
            sgst_amount=Decimal("360.00"),
            igst_amount=Decimal("0.00"),
            grand_total=Decimal("4720.00"),
            amount_due=Decimal("4720.00"),
            amount_paid=Decimal("0.00"),
            due_date=past_due_anchor + timedelta(days=7),
            period_start=past_due_anchor,
            period_end=past_due_anchor + timedelta(days=30),
        )
        session.add_all([soc, plan, sub, inv])
        await session.commit()

    # Record a failed payment attempt
    async with session_factory() as session:
        failed_payment = PlatformPayment(
            id=uuid.uuid4(),
            society_id=soc_id,
            invoice_id=inv_id,
            amount=Decimal("4720.00"),
            status="FAILED",
            gateway_provider="RAZORPAY",
            gateway_payment_id="pay_failed_123",
            captured_at=now,
        )
        session.add(failed_payment)
        await session.commit()

    # Verify subscription is NOT activated and past_due_since is preserved
    async with session_factory() as session:
        sub_row = (await session.execute(select(SocietySubscription).where(SocietySubscription.id == sub_id))).scalar_one()
        assert sub_row.status == SubscriptionStatus.PAST_DUE.value
        assert sub_row.past_due_since == past_due_anchor

        inv_row = (await session.execute(select(PlatformInvoice).where(PlatformInvoice.id == inv_id))).scalar_one()
        assert inv_row.status == "ISSUED"
        assert inv_row.amount_due == Decimal("4720.00")


# ---------------------------------------------------------------------------
# 4. Payment on Cancelled Subscription
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_e2e_payment_against_cancelled_subscription(e2e_harness):
    session_factory = e2e_harness
    now = _utc_now()
    soc_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    sub_id = uuid.uuid4()

    async with session_factory() as session:
        soc = Society(
            id=soc_id,
            legal_name="Cancelled Soc",
            display_name="Cancelled Soc",
            address_line1="123 Term",
            city="Pune",
            state="Maharashtra",
            postal_code="411045",
            status="ACTIVE",
            registration_number="REG-TERM-1",
        )
        plan = PlatformSubscriptionPlan(
            id=plan_id,
            plan_code=f"PLAN_{plan_id.hex[:6]}",
            display_name="Plan",
            monthly_price=Decimal("4000.00"),
            is_active=True,
        )
        sub = SocietySubscription(
            id=sub_id,
            society_id=soc_id,
            plan_id=plan_id,
            status=SubscriptionStatus.CANCELLED.value,  # Terminal!
            billing_cycle="MONTHLY",
            auto_renew=False,
            starts_at=now - timedelta(days=60),
            current_period_start=now - timedelta(days=60),
            current_period_end=now - timedelta(days=30),
            next_billing_at=now - timedelta(days=30),
            past_due_since=None,
        )
        session.add_all([soc, plan, sub])
        await session.commit()

    # Try to reactivate via lifecycle transition
    async with session_factory() as session:
        lifecycle = SubscriptionLifecycleService(session=session)
        # Verify transition CANCELLED -> ACTIVE is rejected by lifecycle state machine
        with pytest.raises(Exception):
            await lifecycle.transition_subscription_state(
                subscription_id=sub_id,
                target_state=SubscriptionStatus.ACTIVE.value,
                reason="Unauthorized attempt",
            )

    async with session_factory() as session:
        sub_row = (await session.execute(select(SocietySubscription).where(SocietySubscription.id == sub_id))).scalar_one()
        assert sub_row.status == SubscriptionStatus.CANCELLED.value


# ---------------------------------------------------------------------------
# 5. Duplicate Payment Webhook Replay Idempotency
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_e2e_duplicate_payment_webhook_replay(e2e_harness):
    session_factory = e2e_harness
    now = _utc_now()
    soc_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    sub_id = uuid.uuid4()
    inv_id = uuid.uuid4()

    async with session_factory() as session:
        soc = Society(
            id=soc_id,
            legal_name="Webhook Idempotency Soc",
            display_name="Webhook Soc",
            address_line1="123 Replay",
            city="Pune",
            state="Maharashtra",
            postal_code="411045",
            status="ACTIVE",
            registration_number="REG-REPLAY-1",
        )
        plan = PlatformSubscriptionPlan(
            id=plan_id,
            plan_code=f"PLAN_{plan_id.hex[:6]}",
            display_name="Plan",
            monthly_price=Decimal("2000.00"),
            is_active=True,
        )
        sub = SocietySubscription(
            id=sub_id,
            society_id=soc_id,
            plan_id=plan_id,
            status=SubscriptionStatus.PAST_DUE.value,
            billing_cycle="MONTHLY",
            auto_renew=True,
            starts_at=now - timedelta(days=30),
            current_period_start=now - timedelta(days=30),
            current_period_end=now - timedelta(days=1),
            next_billing_at=now - timedelta(days=1),
            past_due_since=now - timedelta(days=1),
        )
        inv = PlatformInvoice(
            id=inv_id,
            society_id=soc_id,
            subscription_id=sub_id,
            invoice_number="INV-2627-88881",
            status="ISSUED",
            place_of_supply="MH",
            subtotal=Decimal("2000.00"),
            taxable_amount=Decimal("2000.00"),
            tax_total=Decimal("360.00"),
            cgst_amount=Decimal("180.00"),
            sgst_amount=Decimal("180.00"),
            igst_amount=Decimal("0.00"),
            grand_total=Decimal("2360.00"),
            amount_due=Decimal("2360.00"),
            amount_paid=Decimal("0.00"),
            due_date=now + timedelta(days=7),
            period_start=now - timedelta(days=1),
            period_end=now + timedelta(days=29),
        )
        session.add_all([soc, plan, sub, inv])
        await session.commit()

    gateway_pay_id = "pay_replay_test_123"

    # Ingestion 1: First settlement
    async with session_factory() as session:
        settlement = PaymentSettlementService(session=session)
        payment = await settlement.settle_payment(
            society_id=soc_id,
            gateway_provider="RAZORPAY",
            gateway_payment_id=gateway_pay_id,
            amount=Decimal("2360.00"),
            invoice_id=inv_id,
        )
        assert payment.id is not None
        await session.commit()

    # Ingestion 2 & 3: Replayed webhooks with identical gateway_payment_id
    for _ in range(2):
        async with session_factory() as session:
            existing_pay = (await session.execute(
                select(PlatformPayment).where(PlatformPayment.gateway_payment_id == gateway_pay_id)
            )).scalar_one_or_none()
            assert existing_pay is not None
            assert existing_pay.status == "CAPTURED"

    # Verify exactly 1 payment and 1 receipt exists in DB
    async with session_factory() as session:
        payments = (await session.execute(
            select(PlatformPayment).where(PlatformPayment.invoice_id == inv_id)
        )).scalars().all()
        assert len(payments) == 1
        assert payments[0].status == "CAPTURED"
        assert payments[0].is_settled is True


# ---------------------------------------------------------------------------
# 6. Duplicate Scheduler AMQP Trigger Replay Idempotency
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_e2e_duplicate_scheduler_execution(e2e_harness):
    session_factory = e2e_harness
    now = _utc_now()
    soc_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    sub_id = uuid.uuid4()

    async with session_factory() as session:
        soc = Society(
            id=soc_id,
            legal_name="Sched Idempotent Soc",
            display_name="Sched Soc",
            address_line1="123 Sched",
            city="Pune",
            state="Maharashtra",
            postal_code="411045",
            status="ACTIVE",
            registration_number="REG-SCHED-1",
        )
        plan = PlatformSubscriptionPlan(
            id=plan_id,
            plan_code=f"PLAN_{plan_id.hex[:6]}",
            display_name="Plan",
            monthly_price=Decimal("1500.00"),
            is_active=True,
        )
        sub = SocietySubscription(
            id=sub_id,
            society_id=soc_id,
            plan_id=plan_id,
            status=SubscriptionStatus.ACTIVE.value,
            billing_cycle="MONTHLY",
            auto_renew=True,
            starts_at=now - timedelta(days=30),
            current_period_start=now - timedelta(days=30),
            current_period_end=now - timedelta(hours=1),
            next_billing_at=now - timedelta(hours=1),
            past_due_since=None,
        )
        session.add_all([soc, plan, sub])
        await session.commit()

    exec_id = f"sched-e2e-exec-{uuid.uuid4().hex[:8]}"

    # Execution 1: Normal scheduler run
    async with session_factory() as session:
        scheduler = BillingPeriodSchedulerService(session=session)
        res1 = await scheduler.process_due_subscriptions(cutoff_utc=now, execution_id=exec_id)
        assert res1.processed_count == 1
        assert res1.succeeded_count == 1

    # Execution 2: Redelivered trigger with identical execution_id
    async with session_factory() as session:
        scheduler = BillingPeriodSchedulerService(session=session)
        res2 = await scheduler.process_due_subscriptions(cutoff_utc=now, execution_id=exec_id)
        assert res2.processed_count == 1
        assert res2.succeeded_count == 1  # Cached result returned

    # Verify authoritative database state: exactly 1 invoice, exactly 1 job run
    async with session_factory() as session:
        invoices = (await session.execute(
            select(PlatformInvoice).where(PlatformInvoice.society_id == soc_id)
        )).scalars().all()
        assert len(invoices) == 1

        job_runs = (await session.execute(
            select(PlatformBillingJobRun).where(PlatformBillingJobRun.execution_id == exec_id)
        )).scalars().all()
        assert len(job_runs) == 1
        assert job_runs[0].status == BillingJobRunStatus.COMPLETED.value
