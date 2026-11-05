"""Phase 21E.6 — Stage 2: SaaS Dunning Engine & Grace Period Suspension Unit Tests.

Covers:
1. determine_dunning_stage boundary calculations (Day 0, Day 2, Day 5, Day 7).
2. Day 0 overdue reminder execution (elapsed < 48h, 7 days remaining).
3. Day 2 mid-grace reminder execution (48h <= elapsed < 120h, 5 days remaining).
4. Day 5 final warning execution (120h <= elapsed < 168h, 2 days remaining).
5. Day 7 grace-period expiry & subscription suspension (elapsed >= 168h, 0 days remaining).
6. Idempotency: re-running at the same stage skips execution without duplicate records.
7. Immutable anchor: past_due_since is never modified or reset by repeated executions.
8. Captured payment protection: captured but unsettled payment blocks Day 7 suspension.
9. Late payment recovery: payment settlement reactivates dunning-suspended subscription.
10. Administrative suspension protection: late payment does NOT reactivate administrative suspension.
11. Terminal cancelled state: payment on cancelled subscription never reactivates, marked orphaned.
12. Society decoupling: Society.status remains ACTIVE throughout; administratively suspended societies are excluded.
13. Batch ledger auditing: PlatformBillingJobRun tracks processed, succeeded, skipped, failed counts.
14. Notification provider error resilience: provider failures handled gracefully without DB corruption.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.src.database.base import Base
from apps.api.src.database.models.authorization import Role, RoleAssignment
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.notifications import Notification
from apps.api.src.database.models.platform_billing import (
    PlatformBillingJobRun,
    PlatformDunningAttempt,
    PlatformInvoice,
    PlatformInvoiceSequence,
    PlatformPayment,
    PlatformSubscriptionHistory,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
)
from apps.api.src.notifications.providers.base import (
    CommunicationProvider,
    ProviderMessage,
    ProviderResponse,
)
from apps.api.src.notifications.providers.factory import ProviderFactory
from apps.api.src.subscriptions.automation.dunning_service import (
    DunningEngineService,
    DunningStage,
    compute_advisory_lock_key,
)
from apps.api.src.subscriptions.automation.renewal_service import (
    AutomatedRenewalInvoicingService,
)
from apps.api.src.subscriptions.automation.schemas import BillingJobRunStatus
from apps.api.src.subscriptions.enums import SubscriptionStatus
from apps.api.src.subscriptions.invoicing.numbering import InvoiceNumberingService
from apps.api.src.subscriptions.invoicing.service import PlatformInvoiceService
from apps.api.src.subscriptions.payments.provider import (
    GatewayRefundResponse,
    PaymentGatewayProvider,
)
from apps.api.src.subscriptions.payments.settlement_service import PaymentSettlementService
from apps.api.src.subscriptions.subscription_lifecycle_service import (
    SubscriptionLifecycleService,
)
from apps.api.src.subscriptions.tax import (
    GSTTaxEngine,
    PlaceOfSupplyService,
    tax_config_service,
)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def in_memory_db():
    """In-memory SQLite database for deterministic unit testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest_asyncio.fixture
async def dunning_harness(in_memory_db):
    """Fixture providing initialized services for dunning testing."""
    async with in_memory_db() as session:
        # Seed invoice sequence
        seq = PlatformInvoiceSequence(fiscal_year="2627", current_sequence=0)
        session.add(seq)

        # Seed RBAC roles
        r_admin = Role(id=uuid.uuid4(), code="SOCIETY_ADMIN", name="Society Admin")
        r_treas = Role(id=uuid.uuid4(), code="TREASURER", name="Treasurer")
        session.add_all([r_admin, r_treas])
        await session.commit()

    pos_service = PlaceOfSupplyService()
    tax_engine = GSTTaxEngine(tax_config_service)
    num_service = InvoiceNumberingService()
    invoice_service = PlatformInvoiceService(
        tax_engine=tax_engine,
        pos_service=pos_service,
        numbering_service=num_service,
    )
    renewal_service = AutomatedRenewalInvoicingService(invoice_service=invoice_service)
    return in_memory_db, renewal_service


async def _seed_overdue_tenant(
    session: AsyncSession,
    renewal_service: AutomatedRenewalInvoicingService,
    past_due_hours_ago: float = 1.0,
    society_status: str = "ACTIVE",
    sub_status: str = SubscriptionStatus.PAST_DUE.value,
    plan_price: Decimal = Decimal("2500.00"),
    create_admin_contact: bool = True,
) -> tuple[Society, PlatformSubscriptionPlan, SocietySubscription, PlatformInvoice, User | None]:
    now = _utc_now()
    soc_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    sub_id = uuid.uuid4()

    soc = Society(
        id=soc_id,
        legal_name=f"Overdue Heights {soc_id.hex[:6]}",
        display_name=f"Overdue Soc {soc_id.hex[:6]}",
        address_line1="456 Dunning Road",
        city="Pune",
        state="Maharashtra",
        postal_code="411001",
        status=society_status,
        registration_number="REG-DUN-123",
    )
    plan = PlatformSubscriptionPlan(
        id=plan_id,
        plan_code=f"ENTERPRISE_{plan_id.hex[:6]}",
        display_name="Enterprise Plan",
        monthly_price=plan_price,
        annual_price=plan_price * 10,
        is_active=True,
    )

    past_due_since = now - timedelta(hours=past_due_hours_ago)
    sub = SocietySubscription(
        id=sub_id,
        society_id=soc_id,
        plan_id=plan_id,
        status=sub_status,
        billing_cycle="MONTHLY",
        auto_renew=True,
        starts_at=past_due_since - timedelta(days=30),
        current_period_start=past_due_since - timedelta(days=30),
        current_period_end=past_due_since,
        next_billing_at=past_due_since,
        past_due_since=past_due_since,
    )

    admin_user: User | None = None
    if create_admin_contact:
        user_id = uuid.uuid4()
        phone_suffix = f"{uuid.uuid4().int % 100000000:08d}"
        admin_user = User(
            id=user_id,
            email=f"admin.{soc_id.hex[:6]}@example.com",
            first_name="Admin",
            last_name="Contact",
            display_name="Admin Contact",
            phone=f"+9198{phone_suffix}",
            status="ACTIVE",
        )
        session.add(admin_user)
        # Fetch SOCIETY_ADMIN role
        stmt_role = select(Role).where(Role.code == "SOCIETY_ADMIN")
        role_res = await session.execute(stmt_role)
        role = role_res.scalar_one()

        assignment = RoleAssignment(
            id=uuid.uuid4(),
            user_id=user_id,
            role_id=role.id,
            society_id=soc_id,
            status="ACTIVE",
        )
        session.add(assignment)

    session.add_all([soc, plan, sub])
    await session.commit()

    # Generate active overdue invoice for subscription
    inv_res = await renewal_service.generate_renewal_invoice(
        session=session,
        subscription=sub,
        society=soc,
        period_start=sub.current_period_start,
        period_end=sub.current_period_end,
    )
    stmt_inv = select(PlatformInvoice).where(PlatformInvoice.id == inv_res.id)
    invoice = (await session.execute(stmt_inv)).scalar_one()
    # Ensure invoice is marked OVERDUE with positive amount_due
    invoice.status = "OVERDUE"
    await session.commit()
    await session.refresh(sub)
    await session.refresh(soc)
    await session.refresh(invoice)

    return soc, plan, sub, invoice, admin_user


# ---------------------------------------------------------------------------
# 1. determine_dunning_stage Boundary Tests
# ---------------------------------------------------------------------------
def test_determine_dunning_stage_boundaries():
    """Verify exact 48h, 120h, 168h threshold transitions for dunning milestones."""
    svc = DunningEngineService(session=AsyncMock())
    now = datetime(2026, 11, 3, 12, 0, 0)

    # Day 0: 0 hours elapsed -> DAY_0_REMINDER, 7 days remaining
    stage, rem = svc.determine_dunning_stage(now, now)
    assert stage == DunningStage.DAY_0_REMINDER
    assert rem == 7

    # Day 0: 47 hours 59 mins elapsed -> DAY_0_REMINDER, 7 days remaining
    stage, rem = svc.determine_dunning_stage(now - timedelta(hours=47, minutes=59), now)
    assert stage == DunningStage.DAY_0_REMINDER
    assert rem == 7

    # Day 2: Exactly 48 hours elapsed -> DAY_2_REMINDER, 5 days remaining
    stage, rem = svc.determine_dunning_stage(now - timedelta(hours=48), now)
    assert stage == DunningStage.DAY_2_REMINDER
    assert rem == 5

    # Day 2: 119 hours elapsed -> DAY_2_REMINDER, 5 days remaining
    stage, rem = svc.determine_dunning_stage(now - timedelta(hours=119), now)
    assert stage == DunningStage.DAY_2_REMINDER
    assert rem == 5

    # Day 5: Exactly 120 hours elapsed -> DAY_5_WARNING, 2 days remaining
    stage, rem = svc.determine_dunning_stage(now - timedelta(hours=120), now)
    assert stage == DunningStage.DAY_5_WARNING
    assert rem == 2

    # Day 5: 167 hours elapsed -> DAY_5_WARNING, 2 days remaining
    stage, rem = svc.determine_dunning_stage(now - timedelta(hours=167), now)
    assert stage == DunningStage.DAY_5_WARNING
    assert rem == 2

    # Day 7: Exactly 168 hours elapsed (7 days) -> DAY_7_SUSPENSION, 0 days remaining
    stage, rem = svc.determine_dunning_stage(now - timedelta(hours=168), now)
    assert stage == DunningStage.DAY_7_SUSPENSION
    assert rem == 0

    # Past Day 7: 200 hours elapsed -> DAY_7_SUSPENSION, 0 days remaining
    stage, rem = svc.determine_dunning_stage(now - timedelta(hours=200), now)
    assert stage == DunningStage.DAY_7_SUSPENSION
    assert rem == 0


def test_compute_advisory_lock_key():
    """Verify advisory lock key derives deterministic signed 64-bit integer."""
    k1 = compute_advisory_lock_key("dunning:sub-123")
    k2 = compute_advisory_lock_key("dunning:sub-123")
    k3 = compute_advisory_lock_key("dunning:sub-456")

    assert k1 == k2
    assert k1 != k3
    assert -9223372036854775808 <= k1 <= 9223372036854775807


# ---------------------------------------------------------------------------
# 2. Day 0 Reminder Execution
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dunning_day_0_reminder_flow(dunning_harness):
    session_factory, renewal_service = dunning_harness

    async with session_factory() as session:
        soc, plan, sub, invoice, admin = await _seed_overdue_tenant(
            session=session,
            renewal_service=renewal_service,
            past_due_hours_ago=2.0,  # Day 0
        )
        original_past_due_since = sub.past_due_since

        dunning_service = DunningEngineService(session=session)
        result = await dunning_service.process_single_subscription(
            subscription_id=sub.id,
            cutoff_utc=_utc_now(),
        )

        assert result.status == "REMINDER_SENT"
        assert result.stage == DunningStage.DAY_0_REMINDER.value
        assert result.grace_days_remaining == 7
        assert "EMAIL" in result.channels_dispatched
        assert "IN_APP" in result.channels_dispatched

        # Verify attempt record in DB
        stmt_att = select(PlatformDunningAttempt).where(
            PlatformDunningAttempt.subscription_id == sub.id,
            PlatformDunningAttempt.attempt_type == DunningStage.DAY_0_REMINDER.value,
        )
        res_att = (await session.execute(stmt_att)).scalar_one_or_none()
        assert res_att is not None
        assert res_att.status == "SUCCEEDED"
        assert res_att.grace_days_remaining == 7

        # Invariant: sub remains PAST_DUE, past_due_since untouched
        await session.refresh(sub)
        assert sub.status == SubscriptionStatus.PAST_DUE.value
        assert sub.past_due_since == original_past_due_since


# ---------------------------------------------------------------------------
# 3. Day 2 Mid-Grace Reminder Execution
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dunning_day_2_reminder_flow(dunning_harness):
    session_factory, renewal_service = dunning_harness

    async with session_factory() as session:
        soc, plan, sub, invoice, admin = await _seed_overdue_tenant(
            session=session,
            renewal_service=renewal_service,
            past_due_hours_ago=50.0,  # Day 2
        )

        dunning_service = DunningEngineService(session=session)
        result = await dunning_service.process_single_subscription(
            subscription_id=sub.id,
            cutoff_utc=_utc_now(),
        )

        assert result.status == "REMINDER_SENT"
        assert result.stage == DunningStage.DAY_2_REMINDER.value
        assert result.grace_days_remaining == 5

        # Verify attempt record
        stmt_att = select(PlatformDunningAttempt).where(
            PlatformDunningAttempt.subscription_id == sub.id,
            PlatformDunningAttempt.attempt_type == DunningStage.DAY_2_REMINDER.value,
        )
        att = (await session.execute(stmt_att)).scalar_one_or_none()
        assert att is not None
        assert att.status == "SUCCEEDED"
        assert att.grace_days_remaining == 5


# ---------------------------------------------------------------------------
# 4. Day 5 Final Warning Execution
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dunning_day_5_warning_flow(dunning_harness):
    session_factory, renewal_service = dunning_harness

    async with session_factory() as session:
        soc, plan, sub, invoice, admin = await _seed_overdue_tenant(
            session=session,
            renewal_service=renewal_service,
            past_due_hours_ago=130.0,  # Day 5
        )

        dunning_service = DunningEngineService(session=session)
        result = await dunning_service.process_single_subscription(
            subscription_id=sub.id,
            cutoff_utc=_utc_now(),
        )

        assert result.status == "REMINDER_SENT"
        assert result.stage == DunningStage.DAY_5_WARNING.value
        assert result.grace_days_remaining == 2


# ---------------------------------------------------------------------------
# 5. Day 7 Grace-Period Expiry & Subscription Suspension Flow
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dunning_day_7_suspension_flow(dunning_harness):
    session_factory, renewal_service = dunning_harness

    async with session_factory() as session:
        soc, plan, sub, invoice, admin = await _seed_overdue_tenant(
            session=session,
            renewal_service=renewal_service,
            past_due_hours_ago=170.0,  # Day 7 (168h+)
        )

        dunning_service = DunningEngineService(session=session)
        result = await dunning_service.process_single_subscription(
            subscription_id=sub.id,
            cutoff_utc=_utc_now(),
        )

        assert result.status == "SUSPENDED"
        assert result.stage == DunningStage.DAY_7_SUSPENSION.value
        assert result.grace_days_remaining == 0

        # Verify subscription transitioned to SUSPENDED
        await session.refresh(sub)
        assert sub.status == SubscriptionStatus.SUSPENDED.value
        assert sub.suspended_at is not None

        # Verify society remains ACTIVE (Mandatory Decoupling)
        await session.refresh(soc)
        assert soc.status == "ACTIVE"

        # Verify attempt record in DB
        stmt_att = select(PlatformDunningAttempt).where(
            PlatformDunningAttempt.subscription_id == sub.id,
            PlatformDunningAttempt.attempt_type == DunningStage.DAY_7_SUSPENSION.value,
        )
        att = (await session.execute(stmt_att)).scalar_one_or_none()
        assert att is not None
        assert att.status == "SUCCEEDED"
        assert att.metadata_json.get("action") == "SUSPENSION_EXECUTED"

        # Verify immutable history entry has DUNNING_ prefix
        stmt_hist = (
            select(PlatformSubscriptionHistory)
            .where(
                PlatformSubscriptionHistory.subscription_id == sub.id,
                PlatformSubscriptionHistory.new_status == SubscriptionStatus.SUSPENDED.value,
            )
            .order_by(PlatformSubscriptionHistory.created_at.desc())
        )
        hist = (await session.execute(stmt_hist)).scalars().first()
        assert hist is not None
        assert hist.transition_reason.startswith("DUNNING_")
        assert hist.changed_by is None


# ---------------------------------------------------------------------------
# 6. Idempotency & Re-Execution
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dunning_idempotency_prevents_duplicate_attempts(dunning_harness):
    session_factory, renewal_service = dunning_harness

    async with session_factory() as session:
        soc, plan, sub, invoice, admin = await _seed_overdue_tenant(
            session=session,
            renewal_service=renewal_service,
            past_due_hours_ago=5.0,  # Day 0
        )

        dunning_service = DunningEngineService(session=session)

        # 1st Execution
        res1 = await dunning_service.process_single_subscription(
            subscription_id=sub.id,
            cutoff_utc=_utc_now(),
        )
        assert res1.status == "REMINDER_SENT"

        # 2nd Execution at same cutoff
        res2 = await dunning_service.process_single_subscription(
            subscription_id=sub.id,
            cutoff_utc=_utc_now(),
        )
        assert res2.status == "SKIPPED"
        assert res2.skip_reason == "STAGE_ALREADY_EXECUTED"

        # Exactly 1 attempt record exists
        stmt_att = select(PlatformDunningAttempt).where(
            PlatformDunningAttempt.subscription_id == sub.id,
            PlatformDunningAttempt.attempt_type == DunningStage.DAY_0_REMINDER.value,
        )
        attempts = (await session.execute(stmt_att)).scalars().all()
        assert len(attempts) == 1


# ---------------------------------------------------------------------------
# 7. Immutable Anchor: past_due_since is Never Modified
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dunning_preserves_past_due_since_strictly(dunning_harness):
    session_factory, renewal_service = dunning_harness

    async with session_factory() as session:
        soc, plan, sub, invoice, admin = await _seed_overdue_tenant(
            session=session,
            renewal_service=renewal_service,
            past_due_hours_ago=10.0,
        )
        anchor_date = sub.past_due_since

        dunning_service = DunningEngineService(session=session)

        # Run multiple times
        for _ in range(3):
            await dunning_service.process_single_subscription(
                subscription_id=sub.id,
                cutoff_utc=_utc_now(),
            )
            await session.refresh(sub)
            assert sub.past_due_since == anchor_date


# ---------------------------------------------------------------------------
# 8. Captured Payment Protection at Day 7
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_captured_payment_blocks_day_7_suspension(dunning_harness):
    session_factory, renewal_service = dunning_harness

    async with session_factory() as session:
        soc, plan, sub, invoice, admin = await _seed_overdue_tenant(
            session=session,
            renewal_service=renewal_service,
            past_due_hours_ago=175.0,  # Day 7
        )

        # Record a payment captured by gateway but awaiting settlement reconciliation
        payment = PlatformPayment(
            id=uuid.uuid4(),
            society_id=soc.id,
            invoice_id=invoice.id,
            amount=invoice.amount_due,
            currency_code="INR",
            gateway_provider="RAZORPAY",
            gateway_payment_id="pay_gateway_test_captured",
            status="CAPTURED",
            is_settled=False,  # Unsettled!
            captured_at=_utc_now(),
            created_at=_utc_now(),
        )
        session.add(payment)
        await session.commit()

        dunning_service = DunningEngineService(session=session)
        result = await dunning_service.process_single_subscription(
            subscription_id=sub.id,
            cutoff_utc=_utc_now(),
        )

        # Suspension must be skipped!
        assert result.status == "SKIPPED"
        assert result.skip_reason == "PAYMENT_SETTLEMENT_PENDING"

        # Subscription remains PAST_DUE, not SUSPENDED
        await session.refresh(sub)
        assert sub.status == SubscriptionStatus.PAST_DUE.value


# ---------------------------------------------------------------------------
# 9. Late Payment Recovery: Reactivates Dunning-Suspended Subscription
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_late_payment_recovery_reactivates_dunning_suspended_subscription(dunning_harness):
    session_factory, renewal_service = dunning_harness

    async with session_factory() as session:
        soc, plan, sub, invoice, admin = await _seed_overdue_tenant(
            session=session,
            renewal_service=renewal_service,
            past_due_hours_ago=180.0,
        )

        # 1. Suspend via Dunning Service
        dunning_service = DunningEngineService(session=session)
        res_suspend = await dunning_service.process_single_subscription(
            subscription_id=sub.id,
            cutoff_utc=_utc_now(),
        )
        assert res_suspend.status == "SUSPENDED"

        await session.refresh(sub)
        assert sub.status == SubscriptionStatus.SUSPENDED.value

        # 2. Settle payment for the overdue invoice
        settle_svc = PaymentSettlementService(session=session)
        payment = await settle_svc.settle_payment(
            society_id=soc.id,
            gateway_provider="RAZORPAY",
            gateway_payment_id="pay_late_settle_001",
            amount=invoice.amount_due,
            invoice_id=invoice.id,
        )
        assert payment.status == "CAPTURED"
        assert payment.is_settled is True

        # 3. Verify subscription is restored to ACTIVE!
        await session.refresh(sub)
        assert sub.status == SubscriptionStatus.ACTIVE.value

        # Verify history record confirms dunning suspension lifted
        stmt_hist = (
            select(PlatformSubscriptionHistory)
            .where(
                PlatformSubscriptionHistory.subscription_id == sub.id,
                PlatformSubscriptionHistory.new_status == SubscriptionStatus.ACTIVE.value,
            )
            .order_by(PlatformSubscriptionHistory.created_at.desc())
        )
        hist = (await session.execute(stmt_hist)).scalars().first()
        assert hist is not None
        assert "dunning suspension lifted" in hist.transition_reason


# ---------------------------------------------------------------------------
# 10. Late Payment Rejection: Administrative Suspension is NOT Reactivated
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_late_payment_rejects_administrative_suspension(dunning_harness):
    session_factory, renewal_service = dunning_harness

    async with session_factory() as session:
        soc, plan, sub, invoice, admin = await _seed_overdue_tenant(
            session=session,
            renewal_service=renewal_service,
            past_due_hours_ago=180.0,
        )

        # Administratively suspend subscription (NOT via dunning, by an Admin actor)
        admin_actor_id = uuid.uuid4()
        lifecycle_svc = SubscriptionLifecycleService(session=session)
        await lifecycle_svc.transition_status(
            society_id=soc.id,
            target_status=SubscriptionStatus.SUSPENDED,
            reason="ADMIN_SUSPENSION: Fraud investigation in progress",
            actor_id=admin_actor_id,
        )

        await session.refresh(sub)
        assert sub.status == SubscriptionStatus.SUSPENDED.value

        # Settle invoice payment
        settle_svc = PaymentSettlementService(session=session)
        payment = await settle_svc.settle_payment(
            society_id=soc.id,
            gateway_provider="RAZORPAY",
            gateway_payment_id="pay_admin_settle_002",
            amount=invoice.amount_due,
            invoice_id=invoice.id,
        )
        assert payment.status == "CAPTURED"
        assert payment.is_settled is True

        # Subscription must REMAIN SUSPENDED!
        await session.refresh(sub)
        assert sub.status == SubscriptionStatus.SUSPENDED.value


# ---------------------------------------------------------------------------
# 11. Late Payment on Cancelled Subscription: Marked Orphaned
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_late_payment_on_cancelled_subscription_orphaned(dunning_harness):
    session_factory, renewal_service = dunning_harness

    async with session_factory() as session:
        soc, plan, sub, invoice, admin = await _seed_overdue_tenant(
            session=session,
            renewal_service=renewal_service,
            past_due_hours_ago=200.0,
            sub_status=SubscriptionStatus.CANCELLED.value,
        )

        mock_gateway = MagicMock(spec=PaymentGatewayProvider)
        mock_gateway.initiate_refund = AsyncMock(
            return_value=GatewayRefundResponse(
                refund_id=f"rfnd_{uuid.uuid4().hex[:8]}",
                payment_id="pay_cancelled_orphan_003",
                amount=invoice.amount_due,
                currency="INR",
                status="processed",
            )
        )

        settle_svc = PaymentSettlementService(session=session)
        payment = await settle_svc.settle_payment(
            society_id=soc.id,
            gateway_provider="RAZORPAY",
            gateway_payment_id="pay_cancelled_orphan_003",
            amount=invoice.amount_due,
            invoice_id=invoice.id,
            custom_provider=mock_gateway,
        )

        # Payment recorded and automatically refunded; subscription remains CANCELLED
        assert payment.status == "REFUNDED"
        await session.refresh(sub)
        assert sub.status == SubscriptionStatus.CANCELLED.value


# ---------------------------------------------------------------------------
# 12. Society Status Decoupling & Exclusion
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_society_status_strictly_decoupled_and_excluded(dunning_harness):
    session_factory, renewal_service = dunning_harness

    async with session_factory() as session:
        # 1. Society that is administratively suspended
        soc, plan, sub, invoice, admin = await _seed_overdue_tenant(
            session=session,
            renewal_service=renewal_service,
            past_due_hours_ago=5.0,
            society_status="SUSPENDED",
        )

        dunning_service = DunningEngineService(session=session)

        # Candidate search excludes administratively suspended societies
        candidates = await dunning_service.detect_dunning_candidates(cutoff_utc=_utc_now())
        candidate_sub_ids = [c.id for c in candidates]
        assert sub.id not in candidate_sub_ids


# ---------------------------------------------------------------------------
# 13. Batch Execution Ledger Auditing
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dunning_batch_execution_ledger(dunning_harness):
    session_factory, renewal_service = dunning_harness

    async with session_factory() as session:
        # Seed 2 overdue subscriptions: 1 at Day 0, 1 at Day 7
        soc1, plan1, sub1, inv1, _ = await _seed_overdue_tenant(
            session=session,
            renewal_service=renewal_service,
            past_due_hours_ago=3.0,
        )
        soc2, plan2, sub2, inv2, _ = await _seed_overdue_tenant(
            session=session,
            renewal_service=renewal_service,
            past_due_hours_ago=172.0,
        )

        dunning_service = DunningEngineService(session=session)
        batch_res = await dunning_service.process_dunning_batch(
            cutoff_utc=_utc_now(),
            batch_size=50,
        )

        assert batch_res.status == BillingJobRunStatus.COMPLETED
        assert batch_res.processed_count == 2
        assert batch_res.succeeded_count == 2
        assert batch_res.failed_count == 0

        # Verify PlatformBillingJobRun entry
        stmt_job = select(PlatformBillingJobRun).where(
            PlatformBillingJobRun.id == batch_res.job_run_id,
        )
        job_run = (await session.execute(stmt_job)).scalar_one_or_none()
        assert job_run is not None
        assert job_run.job_type == "DUNNING_EVAL"
        assert job_run.status == "COMPLETED"
        assert job_run.processed_count == 2
        assert job_run.succeeded_count == 2


# ---------------------------------------------------------------------------
# 14. Notification Provider Failure Resilience
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_notification_provider_failure_resilience(dunning_harness):
    session_factory, renewal_service = dunning_harness

    async with session_factory() as session:
        soc, plan, sub, invoice, admin = await _seed_overdue_tenant(
            session=session,
            renewal_service=renewal_service,
            past_due_hours_ago=4.0,
        )

        # Mock a failing provider factory where email fails
        class FailingEmailProvider(CommunicationProvider):
            @property
            def provider_name(self) -> str:
                return "FailingEmail"

            @property
            def channel(self) -> str:
                return "EMAIL"

            async def send(self, message: ProviderMessage) -> ProviderResponse:
                return ProviderResponse(
                    success=False,
                    provider_name="FailingEmail",
                    error_message="SMTP 550 Mailbox unavailable",
                )

        failing_factory = ProviderFactory()
        failing_factory.register_provider("EMAIL", FailingEmailProvider())

        dunning_service = DunningEngineService(session=session, factory=failing_factory)
        result = await dunning_service.process_single_subscription(
            subscription_id=sub.id,
            cutoff_utc=_utc_now(),
        )

        # Even though EMAIL failed, IN_APP succeeded! Attempt is recorded.
        assert result.status == "REMINDER_SENT"
        assert "EMAIL" not in result.channels_dispatched
        assert "IN_APP" in result.channels_dispatched


# ---------------------------------------------------------------------------
# 15. Provider Timeout / Error During Day 7 Suspension (Finding 1 & 2 Remediation)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_provider_timeout_during_day_7_suspension(dunning_harness):
    """Verify provider timeout during Day 7 suspension does NOT roll back suspension."""
    session_factory, renewal_service = dunning_harness

    class TimeoutEmailProvider(CommunicationProvider):
        @property
        def provider_name(self) -> str:
            return "TimeoutEmail"

        @property
        def channel(self) -> str:
            return "EMAIL"

        async def send(self, message: ProviderMessage) -> ProviderResponse:
            raise TimeoutError("SMTP connection timed out after 10000ms")

    async with session_factory() as session:
        soc, plan, sub, invoice, admin = await _seed_overdue_tenant(
            session=session,
            renewal_service=renewal_service,
            past_due_hours_ago=170.0,  # Day 7 (>168h)
        )

        failing_factory = ProviderFactory()
        failing_factory._providers.clear()
        failing_factory.register_provider("EMAIL", TimeoutEmailProvider())
        # No IN_APP, SMS or WHATSAPP registered, so all providers fail

        dunning_service = DunningEngineService(session=session, factory=failing_factory)
        result = await dunning_service.process_single_subscription(
            subscription_id=sub.id,
            cutoff_utc=_utc_now(),
        )

        # Subscription MUST be SUSPENDED
        assert result.status == "SUSPENDED"
        await session.refresh(sub)
        assert sub.status == SubscriptionStatus.SUSPENDED.value

        # Dunning attempt was committed
        att_stmt = select(PlatformDunningAttempt).where(PlatformDunningAttempt.id == result.attempt_id)
        att = (await session.execute(att_stmt)).scalar_one()
        assert att.status == "SUCCEEDED"
        assert att.attempt_type == "DAY_7_SUSPENSION"

        # Outbox notification was saved and set to RETRYING
        notif_stmt = select(Notification).where(Notification.source_event_id == str(result.attempt_id))
        notif = (await session.execute(notif_stmt)).scalar_one()
        assert notif.status == "RETRYING"
        assert notif.category == "BILLING"
        assert notif.priority == "CRITICAL"


# ---------------------------------------------------------------------------
# 16. Provider Exception After Suspension Commits (Finding 1 Remediation)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_provider_exception_after_suspension_commits(dunning_harness):
    """Verify an unexpected exception during dispatch_outbox_notification never rolls back suspension."""
    session_factory, renewal_service = dunning_harness

    async with session_factory() as session:
        soc, plan, sub, invoice, admin = await _seed_overdue_tenant(
            session=session,
            renewal_service=renewal_service,
            past_due_hours_ago=175.0,  # Day 7
        )

        dunning_service = DunningEngineService(session=session)
        # Mock dispatch_outbox_notification to raise a catastrophic RuntimeError
        dunning_service.dispatch_outbox_notification = AsyncMock(side_effect=RuntimeError("Catastrophic network drop"))

        result = await dunning_service.process_single_subscription(
            subscription_id=sub.id,
            cutoff_utc=_utc_now(),
        )

        # Suspension was preserved!
        assert result.status == "SUSPENDED"
        await session.refresh(sub)
        assert sub.status == SubscriptionStatus.SUSPENDED.value

        # Subscription history recorded SUSPENDED
        hist_stmt = select(PlatformSubscriptionHistory).where(
            PlatformSubscriptionHistory.subscription_id == sub.id,
            PlatformSubscriptionHistory.new_status == "SUSPENDED",
        )
        hist = (await session.execute(hist_stmt)).scalar_one_or_none()
        assert hist is not None
        assert "DUNNING_GRACE_PERIOD_EXPIRED" in hist.transition_reason


# ---------------------------------------------------------------------------
# 17. Outbox Event Survives Worker Restart & Succeeds on Retry (Finding 2 Remediation)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_outbox_event_survives_worker_restart_and_succeeds_on_retry(dunning_harness):
    """Verify outbox entry survives worker process crash (auto_drain_outbox=False) and is drained later."""
    session_factory, renewal_service = dunning_harness

    async with session_factory() as session:
        soc, plan, sub, invoice, admin = await _seed_overdue_tenant(
            session=session,
            renewal_service=renewal_service,
            past_due_hours_ago=4.0,  # Day 0
        )

        # 1. First worker processes with auto_drain_outbox=False (or crashes immediately after DB commit)
        dunning_service = DunningEngineService(session=session)
        result = await dunning_service.process_single_subscription(
            subscription_id=sub.id,
            cutoff_utc=_utc_now(),
            auto_drain_outbox=False,
        )

        assert result.status == "REMINDER_SENT"
        assert result.channels_dispatched == []  # Not dispatched yet

        # Verify outbox notification is in QUEUED status
        notif_stmt = select(Notification).where(Notification.source_event_id == str(result.attempt_id))
        notif = (await session.execute(notif_stmt)).scalar_one()
        assert notif.status == "QUEUED"
        outbox_id = notif.id
        await session.commit()

    # 2. Worker restarts with new session/service and drains the outbox
    async with session_factory() as restart_session:
        restart_service = DunningEngineService(session=restart_session)
        drained_count = await restart_service.drain_pending_outbox(
            batch_size=10,
            notification_ids=[outbox_id],
        )
        assert drained_count == 1

        # Check outbox notification is now SENT
        updated_notif = (await restart_session.execute(
            select(Notification).where(Notification.id == outbox_id)
        )).scalar_one()
        assert updated_notif.status == "SENT"

        # Check attempt metadata reflects SENT
        att = (await restart_session.execute(
            select(PlatformDunningAttempt).where(PlatformDunningAttempt.id == result.attempt_id)
        )).scalar_one()
        assert att.metadata_json.get("outbox_status") == "SENT"
        assert "IN_APP" in att.metadata_json.get("channels", [])


# ---------------------------------------------------------------------------
# 18. Bounded Retry Exhaustion (Finding 2 Remediation)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_outbox_bounded_retry_exhaustion(dunning_harness):
    """Verify outbox retries are bounded (max 3) and transition to FAILED upon exhaustion."""
    session_factory, renewal_service = dunning_harness

    class PermanentlyFailingProvider(CommunicationProvider):
        @property
        def provider_name(self) -> str:
            return "FailProv"

        @property
        def channel(self) -> str:
            return "EMAIL"

        async def send(self, message: ProviderMessage) -> ProviderResponse:
            return ProviderResponse(success=False, provider_name="FailProv", error_message="Fatal 500 error")

    async with session_factory() as session:
        soc, plan, sub, invoice, admin = await _seed_overdue_tenant(
            session=session,
            renewal_service=renewal_service,
            past_due_hours_ago=50.0,  # Day 2
        )

        failing_factory = ProviderFactory()
        failing_factory._providers.clear()
        failing_factory.register_provider("EMAIL", PermanentlyFailingProvider())

        dunning_service = DunningEngineService(session=session, factory=failing_factory)
        # Process single subscription with auto_drain_outbox=False
        result = await dunning_service.process_single_subscription(
            subscription_id=sub.id,
            cutoff_utc=_utc_now(),
            auto_drain_outbox=False,
        )

        notif_stmt = select(Notification).where(Notification.source_event_id == str(result.attempt_id))
        notif = (await session.execute(notif_stmt)).scalar_one()
        assert notif.status == "QUEUED"

        # Attempt 1: retry_count becomes 1 -> RETRYING
        status_1, _ = await dunning_service.dispatch_outbox_notification(notif.id)
        assert status_1 == "RETRYING"

        # Attempt 2: retry_count becomes 2 -> RETRYING
        status_2, _ = await dunning_service.dispatch_outbox_notification(notif.id)
        assert status_2 == "RETRYING"

        # Attempt 3: retry_count becomes 3 (>= max_retries 3) -> FAILED
        status_3, _ = await dunning_service.dispatch_outbox_notification(notif.id)
        assert status_3 == "FAILED"

        await session.refresh(notif)
        assert notif.status == "FAILED"

        # Attempt metadata reflects FAILED
        att = (await session.execute(
            select(PlatformDunningAttempt).where(PlatformDunningAttempt.id == result.attempt_id)
        )).scalar_one()
        assert att.metadata_json.get("outbox_status") == "FAILED"

        # Subsequent drain should ignore FAILED notifications
        drained = await dunning_service.drain_pending_outbox(
            notification_ids=[notif.id],
        )
        assert drained == 0


# ---------------------------------------------------------------------------
# 19. Outbox Deduplication Protection (Finding 2 Remediation)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_outbox_deduplication_protection(dunning_harness):
    """Verify already SENT outbox notification cannot be re-dispatched."""
    session_factory, renewal_service = dunning_harness

    class MockEmailProvider(CommunicationProvider):
        def __init__(self):
            self.mock_send = AsyncMock(return_value=ProviderResponse(success=True, provider_name="MockEmail"))

        @property
        def provider_name(self) -> str:
            return "MockEmail"

        @property
        def channel(self) -> str:
            return "EMAIL"

        async def send(self, message: ProviderMessage) -> ProviderResponse:
            return await self.mock_send(message)

    async with session_factory() as session:
        soc, plan, sub, invoice, admin = await _seed_overdue_tenant(
            session=session,
            renewal_service=renewal_service,
            past_due_hours_ago=125.0,  # Day 5
        )

        email_prov = MockEmailProvider()
        factory = ProviderFactory()
        factory.register_provider("EMAIL", email_prov)

        dunning_service = DunningEngineService(session=session, factory=factory)
        result = await dunning_service.process_single_subscription(
            subscription_id=sub.id,
            cutoff_utc=_utc_now(),
            auto_drain_outbox=True,
        )

        notif_stmt = select(Notification).where(Notification.source_event_id == str(result.attempt_id))
        notif = (await session.execute(notif_stmt)).scalar_one()
        assert notif.status == "SENT"
        initial_call_count = email_prov.mock_send.call_count
        assert initial_call_count >= 1

        # Attempt redundant dispatch on already SENT notification
        status, channels = await dunning_service.dispatch_outbox_notification(notif.id)
        assert status == "SENT"
        assert channels == []
        # Mock provider was not called again
        assert email_prov.mock_send.call_count == initial_call_count

