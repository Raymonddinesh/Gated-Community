"""Phase 21E.6 — Stage 1: Automated Billing Period Roll & Renewal Invoicing Unit & Workflow Tests.

Covers:
1. Monthly billing period processing and statutory invoice generation.
2. Annual billing period processing and statutory invoice generation.
3. Month-end clamping (Jan 31 -> Feb 28 -> Mar 31) and anchor-day preservation.
4. Leap-year handling (Feb 29 leap year -> Feb 28 common year).
5. Future billing period exclusion (next_billing_at > cutoff_utc).
6. Cancelled subscription exclusion (status == 'CANCELLED').
7. Administratively suspended society exclusion (Society.status == 'SUSPENDED').
8. Duplicate invoice prevention (idempotent short-circuit on retry).
9. Scheduler retry after worker failure (recovering without duplicate invoice).
10. Atomic invoice and tax snapshot persistence.
11. Billing period advancement verification.
12. PlatformBillingJobRun execution ledger auditing.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.src.database.base import Base
from apps.api.src.database.models.platform_billing import (
    PlatformBillingJobRun,
    PlatformInvoice,
    PlatformInvoiceSequence,
    PlatformSubscriptionAuditLog,
    PlatformSubscriptionHistory,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
)
from apps.api.src.subscriptions.automation.renewal_service import (
    AutomatedRenewalInvoicingService,
)
from apps.api.src.subscriptions.automation.scheduler_service import (
    BillingPeriodSchedulerService,
)
from apps.api.src.subscriptions.automation.schemas import BillingJobRunStatus
from apps.api.src.subscriptions.billing_period_service import BillingPeriodService
from apps.api.src.subscriptions.enums import SubscriptionStatus
from apps.api.src.subscriptions.grace_period_service import GracePeriodService
from apps.api.src.subscriptions.invoicing.numbering import InvoiceNumberingService
from apps.api.src.subscriptions.invoicing.service import PlatformInvoiceService
from apps.api.src.subscriptions.payments.settlement_service import PaymentSettlementService
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
async def scheduler_harness(in_memory_db):
    """Fixture providing initialized services for billing scheduler testing."""
    async with in_memory_db() as session:
        # Seed initial financial year sequence for tests
        seq = PlatformInvoiceSequence(fiscal_year="2627", current_sequence=0)
        session.add(seq)
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
    return in_memory_db, renewal_service, invoice_service


async def _seed_test_tenant(
    session: AsyncSession,
    plan_code: str = "PRO_MONTHLY",
    billing_cycle: str = "MONTHLY",
    monthly_price: Decimal = Decimal("2000.00"),
    annual_price: Decimal = Decimal("20000.00"),
    society_status: str = "ACTIVE",
    sub_status: str = "ACTIVE",
    auto_renew: bool = True,
    starts_at: datetime | None = None,
    current_period_start: datetime | None = None,
    current_period_end: datetime | None = None,
    next_billing_at: datetime | None = None,
    state: str = "Maharashtra",
) -> tuple[Society, PlatformSubscriptionPlan, SocietySubscription]:
    now = _utc_now()
    soc_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    sub_id = uuid.uuid4()

    soc = Society(
        id=soc_id,
        legal_name=f"Test Society {soc_id.hex[:6]}",
        display_name=f"Test Soc {soc_id.hex[:6]}",
        address_line1="123 Tech Lane",
        city="Mumbai",
        state=state,
        postal_code="400001",
        status=society_status,
        registration_number="REG-12345",
    )
    plan = PlatformSubscriptionPlan(
        id=plan_id,
        plan_code=f"{plan_code}_{plan_id.hex[:6]}",
        display_name="Professional Plan",
        monthly_price=monthly_price,
        annual_price=annual_price,
        is_active=True,
    )

    p_start = current_period_start or now - timedelta(days=30)
    p_end = current_period_end or now
    nxt = next_billing_at if next_billing_at is not None else p_end
    st = starts_at or p_start

    sub = SocietySubscription(
        id=sub_id,
        society_id=soc_id,
        plan_id=plan_id,
        status=sub_status,
        billing_cycle=billing_cycle,
        auto_renew=auto_renew,
        starts_at=st,
        current_period_start=p_start,
        current_period_end=p_end,
        next_billing_at=nxt,
    )

    session.add_all([soc, plan, sub])
    await session.commit()
    await session.refresh(sub)
    await session.refresh(soc)
    await session.refresh(plan)
    return soc, plan, sub


# =============================================================================
# 1. Monthly Billing Period Processing
# =============================================================================
@pytest.mark.asyncio
async def test_monthly_billing_period_roll_and_invoicing(scheduler_harness):
    session_factory, renewal_service, invoice_service = scheduler_harness
    now = _utc_now()

    async with session_factory() as session:
        soc, plan, sub = await _seed_test_tenant(
            session,
            billing_cycle="MONTHLY",
            monthly_price=Decimal("2500.00"),
            current_period_start=now - timedelta(days=30),
            current_period_end=now,
            next_billing_at=now,
        )

        scheduler = BillingPeriodSchedulerService(session, renewal_service=renewal_service)
        result = await scheduler.process_due_subscriptions(cutoff_utc=now + timedelta(seconds=1))

        assert result.processed_count == 1
        assert result.succeeded_count == 1
        assert result.failed_count == 0
        assert result.status == BillingJobRunStatus.COMPLETED

        # Verify subscription was advanced
        await session.refresh(sub)
        assert sub.current_period_start == now
        assert sub.current_period_end > now
        assert sub.next_billing_at == sub.current_period_end

        # Verify invoice was created and finalized
        stmt_inv = select(PlatformInvoice).where(PlatformInvoice.subscription_id == sub.id)
        invoices = (await session.execute(stmt_inv)).scalars().all()
        assert len(invoices) == 1
        inv = invoices[0]
        assert inv.status == "ISSUED"
        assert inv.invoice_number is not None
        assert inv.invoice_number.startswith("SS-2627-")
        assert inv.subtotal == Decimal("2500.00")
        assert inv.tax_total > Decimal("0.00")
        assert inv.grand_total == inv.subtotal + inv.tax_total
        assert inv.idempotency_key is not None

        # Verify Job Run ledger
        stmt_job = select(PlatformBillingJobRun).where(PlatformBillingJobRun.execution_id == result.execution_id)
        job_run = (await session.execute(stmt_job)).scalar_one()
        assert job_run.status == "COMPLETED"
        assert job_run.succeeded_count == 1


# =============================================================================
# 2. Annual Billing Period Processing
# =============================================================================
@pytest.mark.asyncio
async def test_annual_billing_period_roll_and_invoicing(scheduler_harness):
    session_factory, renewal_service, invoice_service = scheduler_harness
    now = _utc_now()

    async with session_factory() as session:
        soc, plan, sub = await _seed_test_tenant(
            session,
            billing_cycle="ANNUAL",
            annual_price=Decimal("30000.00"),
            current_period_start=now - timedelta(days=365),
            current_period_end=now,
            next_billing_at=now,
        )

        scheduler = BillingPeriodSchedulerService(session, renewal_service=renewal_service)
        result = await scheduler.process_due_subscriptions(cutoff_utc=now + timedelta(seconds=1))

        assert result.succeeded_count == 1
        await session.refresh(sub)
        assert sub.current_period_start == now
        # Annual period rolls ~365/366 days
        diff_days = (sub.current_period_end - sub.current_period_start).days
        assert diff_days in (365, 366)

        stmt_inv = select(PlatformInvoice).where(PlatformInvoice.subscription_id == sub.id)
        inv = (await session.execute(stmt_inv)).scalar_one()
        assert inv.status == "ISSUED"
        assert inv.subtotal == Decimal("30000.00")


# =============================================================================
# 3. Month-End Clamping and Anchor-Day Preservation
# =============================================================================
@pytest.mark.asyncio
async def test_month_end_clamping_and_anchor_day_preservation():
    """Verify Jan 31 -> Feb 28 -> Mar 31 anchor day preservation."""
    # Jan 31 at 10:00 UTC
    jan_31_utc = datetime(2027, 1, 31, 10, 0, 0, tzinfo=UTC)
    anchor_day = BillingPeriodService.to_ist(jan_31_utc).day
    assert anchor_day == 31

    # Roll from Jan 31 -> Feb (common year 2027 has 28 days)
    start_feb, end_feb = BillingPeriodService.calculate_next_billing_period(
        current_period_end_utc=jan_31_utc,
        billing_cycle="MONTHLY",
        original_anchor_day=anchor_day,
    )
    ist_end_feb = BillingPeriodService.to_ist(end_feb)
    assert ist_end_feb.month == 2
    assert ist_end_feb.day == 28

    # Roll from Feb 28 -> March (preserves anchor day 31!)
    start_mar, end_mar = BillingPeriodService.calculate_next_billing_period(
        current_period_end_utc=end_feb,
        billing_cycle="MONTHLY",
        original_anchor_day=anchor_day,
    )
    ist_end_mar = BillingPeriodService.to_ist(end_mar)
    assert ist_end_mar.month == 3
    assert ist_end_mar.day == 31, "Anchor day 31 must be restored for March!"


# =============================================================================
# 4. Leap-Year Handling
# =============================================================================
@pytest.mark.asyncio
async def test_leap_year_handling():
    """Verify leap year Feb 29 behavior."""
    # Leap year 2028: Jan 31 -> Feb 29
    jan_31_2028 = datetime(2028, 1, 31, 12, 0, 0, tzinfo=UTC)
    start_feb_28, end_feb_28 = BillingPeriodService.calculate_next_billing_period(
        current_period_end_utc=jan_31_2028,
        billing_cycle="MONTHLY",
        original_anchor_day=31,
    )
    ist_end_feb_28 = BillingPeriodService.to_ist(end_feb_28)
    assert ist_end_feb_28.month == 2
    assert ist_end_feb_28.day == 29, "Leap year February must clamp to 29th!"

    # Annual leap year renewal: Feb 29, 2028 -> Feb 28, 2029 (common year)
    feb_29_2028 = datetime(2028, 2, 29, 12, 0, 0, tzinfo=UTC)
    start_ann, end_ann = BillingPeriodService.calculate_next_billing_period(
        current_period_end_utc=feb_29_2028,
        billing_cycle="ANNUAL",
        original_anchor_day=29,
    )
    ist_end_ann = BillingPeriodService.to_ist(end_ann)
    assert ist_end_ann.year == 2029
    assert ist_end_ann.month == 2
    assert ist_end_ann.day == 28, "Leap year Feb 29 annual renewal clamps to Feb 28 in common year!"


# =============================================================================
# 5. Future Billing Period Exclusion
# =============================================================================
@pytest.mark.asyncio
async def test_future_billing_period_exclusion(scheduler_harness):
    session_factory, renewal_service, _ = scheduler_harness
    now = _utc_now()
    future_date = now + timedelta(days=15)

    async with session_factory() as session:
        soc, plan, sub = await _seed_test_tenant(
            session,
            current_period_start=now,
            current_period_end=future_date,
            next_billing_at=future_date,
        )

        scheduler = BillingPeriodSchedulerService(session, renewal_service=renewal_service)
        result = await scheduler.process_due_subscriptions(cutoff_utc=now)

        assert result.processed_count == 0
        assert result.succeeded_count == 0
        # Assert subscription untouched
        await session.refresh(sub)
        assert sub.next_billing_at == future_date


# =============================================================================
# 6. Cancelled Subscription Exclusion
# =============================================================================
@pytest.mark.asyncio
async def test_cancelled_subscription_exclusion(scheduler_harness):
    session_factory, renewal_service, _ = scheduler_harness
    now = _utc_now()

    async with session_factory() as session:
        soc, plan, sub = await _seed_test_tenant(
            session,
            sub_status="CANCELLED",
            current_period_start=now - timedelta(days=30),
            current_period_end=now,
            next_billing_at=now,
        )

        scheduler = BillingPeriodSchedulerService(session, renewal_service=renewal_service)
        result = await scheduler.process_due_subscriptions(cutoff_utc=now + timedelta(seconds=1))

        # CANCELLED status is filtered out at candidate query level
        assert result.processed_count == 0
        await session.refresh(sub)
        assert sub.status == "CANCELLED"
        assert sub.current_period_end == now


# =============================================================================
# 7. Administratively Suspended Society Handling
# =============================================================================
@pytest.mark.asyncio
async def test_administratively_suspended_society_exclusion(scheduler_harness):
    session_factory, renewal_service, _ = scheduler_harness
    now = _utc_now()

    async with session_factory() as session:
        soc, plan, sub = await _seed_test_tenant(
            session,
            society_status="SUSPENDED",  # Administratively locked by Super Admin
            sub_status="ACTIVE",
            current_period_start=now - timedelta(days=30),
            current_period_end=now,
            next_billing_at=now,
        )

        scheduler = BillingPeriodSchedulerService(session, renewal_service=renewal_service)
        result = await scheduler.process_due_subscriptions(cutoff_utc=now + timedelta(seconds=1))

        # Administratively suspended societies are excluded
        assert result.processed_count == 0
        await session.refresh(sub)
        assert sub.next_billing_at == now

        # Ensure zero invoices generated
        stmt_inv = select(PlatformInvoice).where(PlatformInvoice.subscription_id == sub.id)
        invoices = (await session.execute(stmt_inv)).scalars().all()
        assert len(invoices) == 0


# =============================================================================
# 8. Duplicate Invoice Prevention & Idempotency
# =============================================================================
@pytest.mark.asyncio
async def test_duplicate_invoice_prevention(scheduler_harness):
    session_factory, renewal_service, _ = scheduler_harness
    now = _utc_now()

    async with session_factory() as session:
        soc, plan, sub = await _seed_test_tenant(
            session,
            current_period_start=now - timedelta(days=30),
            current_period_end=now,
            next_billing_at=now,
        )

        new_period_start, new_period_end = BillingPeriodService.calculate_next_billing_period(
            current_period_end_utc=now,
            billing_cycle=sub.billing_cycle,
        )
        idempotency_key = f"renewal:{sub.id}:{new_period_start.isoformat()}:{new_period_end.isoformat()}"

        # First generation call
        inv_1 = await renewal_service.generate_renewal_invoice(
            session=session,
            subscription=sub,
            society=soc,
            period_start=new_period_start,
            period_end=new_period_end,
            idempotency_key=idempotency_key,
        )
        assert inv_1.invoice_number is not None

        # Second generation call for exact same period & idempotency key
        inv_2 = await renewal_service.generate_renewal_invoice(
            session=session,
            subscription=sub,
            society=soc,
            period_start=new_period_start,
            period_end=new_period_end,
            idempotency_key=idempotency_key,
        )

        # Must return the exact same invoice without creating a duplicate
        assert inv_2.id == inv_1.id
        assert inv_2.invoice_number == inv_1.invoice_number

        stmt = select(PlatformInvoice).where(PlatformInvoice.subscription_id == sub.id)
        all_invoices = (await session.execute(stmt)).scalars().all()
        assert len(all_invoices) == 1


# =============================================================================
# 9. Scheduler Recovery After Simulated Worker Failure
# =============================================================================
@pytest.mark.asyncio
async def test_scheduler_recovery_after_worker_crash(scheduler_harness):
    """Simulate worker crash after invoice creation but before next_billing_at advancement.

    On subsequent scheduler run, the service must detect the existing invoice,
    avoid duplicate creation, and safely advance next_billing_at.
    """
    session_factory, renewal_service, _ = scheduler_harness
    now = _utc_now()

    async with session_factory() as session:
        soc, plan, sub = await _seed_test_tenant(
            session,
            current_period_start=now - timedelta(days=30),
            current_period_end=now,
            next_billing_at=now,
        )

        # Worker created invoice but crashed before updating subscription table:
        ist_starts = BillingPeriodService.to_ist(sub.starts_at)
        anchor_day = ist_starts.day
        new_period_start, new_period_end = BillingPeriodService.calculate_next_billing_period(
            current_period_end_utc=now,
            billing_cycle=sub.billing_cycle,
            original_anchor_day=anchor_day,
        )
        if new_period_start.tzinfo is not None:
            new_period_start = new_period_start.replace(tzinfo=None)
        if new_period_end.tzinfo is not None:
            new_period_end = new_period_end.replace(tzinfo=None)
        idempotency_key = f"renewal:{sub.id}:{new_period_start.isoformat()}:{new_period_end.isoformat()}"

        inv_pre = await renewal_service.generate_renewal_invoice(
            session=session,
            subscription=sub,
            society=soc,
            period_start=new_period_start,
            period_end=new_period_end,
            idempotency_key=idempotency_key,
        )
        await session.commit()

        # At this point: invoice exists, but sub.next_billing_at is STILL 'now'
        await session.refresh(sub)
        assert sub.next_billing_at == now

        # Next scheduler run detects the subscription
        scheduler = BillingPeriodSchedulerService(session, renewal_service=renewal_service)
        result = await scheduler.process_due_subscriptions(cutoff_utc=now + timedelta(seconds=1))

        assert result.succeeded_count == 1
        assert result.results[0].invoice_id == inv_pre.id
        assert result.results[0].invoice_number == inv_pre.invoice_number

        # Verify next_billing_at was safely advanced
        await session.refresh(sub)
        assert sub.next_billing_at == new_period_end
        assert sub.current_period_start == new_period_start
        assert sub.current_period_end == new_period_end

        # Verify total invoices remains exactly 1
        stmt = select(PlatformInvoice).where(PlatformInvoice.subscription_id == sub.id)
        assert len((await session.execute(stmt)).scalars().all()) == 1


# =============================================================================
# 10. Atomic Invoice and Tax Snapshot Persistence
# =============================================================================
@pytest.mark.asyncio
async def test_atomic_invoice_and_tax_snapshot_persistence(scheduler_harness):
    session_factory, renewal_service, invoice_service = scheduler_harness
    now = _utc_now()

    async with session_factory() as session:
        soc, plan, sub = await _seed_test_tenant(
            session,
            state="Karnataka",  # Supplier state is Karnataka -> Intra-state CGST+SGST
            current_period_start=now - timedelta(days=30),
            current_period_end=now,
            next_billing_at=now,
        )

        scheduler = BillingPeriodSchedulerService(session, renewal_service=renewal_service)
        result = await scheduler.process_due_subscriptions(cutoff_utc=now + timedelta(seconds=1))

        inv_id = result.results[0].invoice_id
        assert inv_id is not None

        # Verify cryptographic tax snapshot audit log
        stmt_audit = select(PlatformSubscriptionAuditLog).where(
            PlatformSubscriptionAuditLog.society_id == soc.id,
            PlatformSubscriptionAuditLog.entity_id == inv_id,
            PlatformSubscriptionAuditLog.entity_type == "INVOICE_TAX_SNAPSHOT",
        )
        audit_log = (await session.execute(stmt_audit)).scalar_one_or_none()
        assert audit_log is not None
        assert audit_log.after_state is not None
        snapshot_data = audit_log.after_state
        assert "integrity_hash" in snapshot_data
        assert "taxable_value" in snapshot_data
        assert "total_tax" in snapshot_data
        assert snapshot_data["sac_code"] == "998313"

        # Verify tax snapshot verification service
        verif = await invoice_service.verify_invoice_tax_snapshot(session, inv_id)
        assert verif.is_valid is True
        assert verif.snapshot_hash == snapshot_data["integrity_hash"]


# =============================================================================
# 11. Trial Expiration, Grace Period, and Payment Settlement Tests
# =============================================================================
@pytest.mark.asyncio
async def test_expired_trial_transitions_to_past_due_with_grace_period(scheduler_harness):
    """Expired TRIAL with auto_renew=True transitions to PAST_DUE with 7-day grace period upon renewal roll."""
    session_factory, renewal_service, _ = scheduler_harness
    now = _utc_now()

    async with session_factory() as session:
        soc, plan, sub = await _seed_test_tenant(
            session,
            sub_status="TRIAL",
            auto_renew=True,
            current_period_start=now - timedelta(days=14),
            current_period_end=now,
            next_billing_at=now,
        )

        scheduler = BillingPeriodSchedulerService(session, renewal_service=renewal_service)
        result = await scheduler.process_due_subscriptions(cutoff_utc=now + timedelta(seconds=1))

        assert result.succeeded_count == 1
        await session.refresh(sub)

        # 1. Verification: Status is PAST_DUE, never prematurely ACTIVE
        assert sub.status == SubscriptionStatus.PAST_DUE.value, (
            "Expiring TRIAL must transition to PAST_DUE awaiting payment settlement, never prematurely ACTIVE!"
        )

        # 2. Verification: Renewal invoice issued in ISSUED status and unpaid
        inv_id = result.results[0].invoice_id
        assert inv_id is not None
        stmt_inv = select(PlatformInvoice).where(PlatformInvoice.id == inv_id)
        invoice = (await session.execute(stmt_inv)).scalar_one()
        assert invoice.status == "ISSUED"
        assert invoice.amount_due == invoice.grand_total
        assert invoice.amount_paid == Decimal("0.00")

        # 3. Verification: 7-day grace period initialized correctly
        assert sub.past_due_since is not None
        grace_eval = GracePeriodService().evaluate_grace_period(
            due_date=sub.past_due_since,
            as_of_time=now,
        )
        assert grace_eval.is_expired is False
        assert grace_eval.seconds_remaining > 0
        expected_expiry = (sub.past_due_since + timedelta(days=7)).replace(tzinfo=UTC)
        assert GracePeriodService.calculate_grace_expiry(sub.past_due_since) == expected_expiry


@pytest.mark.asyncio
async def test_repeated_scheduler_execution_does_not_extend_grace_period(scheduler_harness):
    """Repeated scheduler runs must not reset or extend the 7-day grace period."""
    session_factory, renewal_service, _ = scheduler_harness
    now = _utc_now()

    async with session_factory() as session:
        soc, plan, sub = await _seed_test_tenant(
            session,
            sub_status="TRIAL",
            auto_renew=True,
            current_period_start=now - timedelta(days=14),
            current_period_end=now,
            next_billing_at=now,
        )

        scheduler = BillingPeriodSchedulerService(session, renewal_service=renewal_service)
        # First execution
        await scheduler.process_due_subscriptions(cutoff_utc=now + timedelta(seconds=1))
        await session.refresh(sub)
        initial_past_due_since = sub.past_due_since
        assert initial_past_due_since is not None

        # Simulate second execution 1 hour later
        later = now + timedelta(hours=1)
        sub.next_billing_at = later - timedelta(minutes=1)  # force eligibility if applicable
        await session.commit()

        await scheduler.process_due_subscriptions(cutoff_utc=later)
        await session.refresh(sub)

        # Ensure past_due_since was not reset to later time
        assert sub.past_due_since == initial_past_due_since, (
            "Scheduler retries must preserve original past_due_since and never extend the grace period!"
        )


@pytest.mark.asyncio
async def test_payment_settlement_transitions_past_due_to_active(scheduler_harness):
    """Confirmed payment settlement transitions PAST_DUE trial subscription to ACTIVE and clears grace period."""
    session_factory, renewal_service, _ = scheduler_harness
    now = _utc_now()

    async with session_factory() as session:
        soc, plan, sub = await _seed_test_tenant(
            session,
            sub_status="TRIAL",
            auto_renew=True,
            current_period_start=now - timedelta(days=14),
            current_period_end=now,
            next_billing_at=now,
        )

        scheduler = BillingPeriodSchedulerService(session, renewal_service=renewal_service)
        result = await scheduler.process_due_subscriptions(cutoff_utc=now + timedelta(seconds=1))
        inv_id = result.results[0].invoice_id
        await session.refresh(sub)
        assert sub.status == "PAST_DUE"

        stmt_inv = select(PlatformInvoice).where(PlatformInvoice.id == inv_id)
        invoice = (await session.execute(stmt_inv)).scalar_one()

        # Execute authoritative payment settlement
        settlement_service = PaymentSettlementService(session)
        payment = await settlement_service.settle_payment(
            society_id=soc.id,
            gateway_provider="RAZORPAY",
            gateway_payment_id=f"pay_{uuid.uuid4().hex[:10]}",
            amount=invoice.grand_total,
            invoice_id=invoice.id,
        )
        assert payment.status == "CAPTURED"
        assert payment.is_settled is True

        await session.refresh(sub)
        await session.refresh(invoice)

        # Verify transition to ACTIVE and invoice to PAID
        assert invoice.status == "PAID"
        assert invoice.amount_due == Decimal("0.00")
        assert sub.status == "ACTIVE", "Subscription must transition to ACTIVE only upon confirmed settlement!"
        assert sub.past_due_since is None, "Confirmed settlement must clear past_due_since flag!"


@pytest.mark.asyncio
async def test_failed_payment_does_not_activate_subscription(scheduler_harness):
    """Unsettled / unpaid invoice leaves subscription in PAST_DUE status without activation."""
    session_factory, renewal_service, _ = scheduler_harness
    now = _utc_now()

    async with session_factory() as session:
        soc, plan, sub = await _seed_test_tenant(
            session,
            sub_status="TRIAL",
            auto_renew=True,
            current_period_start=now - timedelta(days=14),
            current_period_end=now,
            next_billing_at=now,
        )

        scheduler = BillingPeriodSchedulerService(session, renewal_service=renewal_service)
        await scheduler.process_due_subscriptions(cutoff_utc=now + timedelta(seconds=1))
        await session.refresh(sub)

        # Subscription remains PAST_DUE in the absence of settlement
        assert sub.status == "PAST_DUE"
        assert sub.past_due_since is not None


@pytest.mark.asyncio
async def test_administratively_suspended_society_remains_suspended_after_payment(scheduler_harness):
    """Administrative society suspension is decoupled from subscription status and is never reactivated by payment."""
    session_factory, renewal_service, _ = scheduler_harness
    now = _utc_now()

    async with session_factory() as session:
        soc, plan, sub = await _seed_test_tenant(
            session,
            society_status="SUSPENDED",  # Administratively SUSPENDED society
            sub_status="PAST_DUE",
            current_period_start=now - timedelta(days=30),
            current_period_end=now,
            next_billing_at=now + timedelta(days=30),
        )
        sub.past_due_since = now - timedelta(days=2)
        await session.commit()

        # Create an unpaid issued invoice
        inv = PlatformInvoice(
            id=uuid.uuid4(),
            society_id=soc.id,
            subscription_id=sub.id,
            billing_cycle="MONTHLY",
            period_start=now - timedelta(days=30),
            period_end=now,
            subtotal=Decimal("2000.00"),
            taxable_amount=Decimal("2000.00"),
            tax_total=Decimal("360.00"),
            grand_total=Decimal("2360.00"),
            amount_due=Decimal("2360.00"),
            status="ISSUED",
            due_date=now.date(),
            place_of_supply="Maharashtra",
            idempotency_key=f"inv-susp-{uuid.uuid4().hex[:8]}",
        )
        session.add(inv)
        await session.commit()

        # Settle the invoice
        settlement_service = PaymentSettlementService(session)
        await settlement_service.settle_payment(
            society_id=soc.id,
            gateway_provider="RAZORPAY",
            gateway_payment_id=f"pay_susp_{uuid.uuid4().hex[:8]}",
            amount=inv.grand_total,
            invoice_id=inv.id,
        )

        await session.refresh(soc)
        await session.refresh(sub)

        # Invariant: Subscription becomes ACTIVE, but Society remains SUSPENDED
        assert sub.status == "ACTIVE"
        assert soc.status == "SUSPENDED", (
            "Payment settlement must NEVER reactivate an administratively SUSPENDED society!"
        )


@pytest.mark.asyncio
async def test_expired_trial_with_auto_renew_false_does_not_generate_invoice_or_grace_period(scheduler_harness):
    """Expired TRIAL with auto_renew=False must NOT generate renewal invoice, must NOT set PAST_DUE,

    must NOT initiate grace period, and must transition cleanly to terminal CANCELLED state.
    """
    session_factory, renewal_service, _ = scheduler_harness
    now = _utc_now()

    async with session_factory() as session:
        soc, plan, sub = await _seed_test_tenant(
            session,
            sub_status="TRIAL",
            auto_renew=False,  # auto_renew is FALSE
            current_period_start=now - timedelta(days=14),
            current_period_end=now,
            next_billing_at=now,
        )

        scheduler = BillingPeriodSchedulerService(session, renewal_service=renewal_service)
        result = await scheduler.process_due_subscriptions(cutoff_utc=now + timedelta(seconds=1))

        # 1. Verification: Execution counts
        assert result.processed_count == 1
        assert result.succeeded_count == 1
        assert result.failed_count == 0
        assert result.skipped_count == 0

        roll_res = result.results[0]
        assert roll_res.status == "CANCELLED"
        assert roll_res.skip_reason == "TRIAL_EXPIRED_WITHOUT_RENEWAL"
        assert roll_res.invoice_id is None, "No invoice may be created for auto_renew=False trial!"
        assert roll_res.invoice_number is None

        await session.refresh(sub)

        # 2. Verification: Status is CANCELLED, NEVER PAST_DUE or ACTIVE
        assert sub.status == SubscriptionStatus.CANCELLED.value
        assert sub.cancelled_at is not None
        assert "Trial expired with auto_renew=False" in (sub.cancellation_reason or "")
        assert sub.auto_renew is False

        # 3. Verification: Grace period NOT initiated
        assert sub.past_due_since is None, "past_due_since must remain None when auto_renew=False!"

        # 4. Verification: Zero invoices generated in database
        stmt_inv = select(PlatformInvoice).where(PlatformInvoice.subscription_id == sub.id)
        invoices = (await session.execute(stmt_inv)).scalars().all()
        assert len(invoices) == 0, f"Expected 0 invoices, found {len(invoices)}!"

        # 5. Verification: PlatformSubscriptionHistory record
        stmt_hist = (
            select(PlatformSubscriptionHistory)
            .where(PlatformSubscriptionHistory.subscription_id == sub.id)
            .order_by(PlatformSubscriptionHistory.effective_at.desc())
        )
        hist = (await session.execute(stmt_hist)).scalars().first()
        assert hist is not None
        assert hist.previous_status == "TRIAL"
        assert hist.new_status == "CANCELLED"
        assert "Trial expired with auto_renew=False" in hist.transition_reason

        # 6. Verification: PlatformSubscriptionAuditLog record
        stmt_audit = (
            select(PlatformSubscriptionAuditLog)
            .where(PlatformSubscriptionAuditLog.entity_id == sub.id)
            .order_by(PlatformSubscriptionAuditLog.created_at.desc())
        )
        audit = (await session.execute(stmt_audit)).scalars().first()
        assert audit is not None
        assert audit.action == "TRIAL_EXPIRED_CANCELLED"
        assert audit.before_state["status"] == "TRIAL"
        assert audit.after_state["status"] == "CANCELLED"
        assert audit.after_state["past_due_since"] is None

        # 7. Verification: Repeated scheduler execution is fully idempotent
        repeat_result = await scheduler.process_due_subscriptions(cutoff_utc=now + timedelta(hours=2))
        assert repeat_result.processed_count == 0, "Cancelled trial must not be re-processed!"
        assert repeat_result.succeeded_count == 0

        # Invoices remain 0
        invoices_after = (await session.execute(stmt_inv)).scalars().all()
        assert len(invoices_after) == 0


@pytest.mark.asyncio
async def test_roll_single_subscription_active_with_auto_renew_false_is_skipped(scheduler_harness):
    """Direct invocation of roll_single_subscription on an ACTIVE subscription with auto_renew=False is skipped."""
    session_factory, renewal_service, _ = scheduler_harness
    now = _utc_now()

    async with session_factory() as session:
        soc, plan, sub = await _seed_test_tenant(
            session,
            sub_status="ACTIVE",
            auto_renew=False,
            current_period_start=now - timedelta(days=30),
            current_period_end=now,
            next_billing_at=now,
        )

        scheduler = BillingPeriodSchedulerService(session, renewal_service=renewal_service)
        roll_res = await scheduler.roll_single_subscription(
            subscription_id=sub.id,
            cutoff_utc=now + timedelta(seconds=1),
            execution_id="test-manual-active-non-renew",
        )

        assert roll_res.status == "SKIPPED"
        assert roll_res.skip_reason == "AUTO_RENEW_DISABLED"
        assert roll_res.invoice_id is None

        # Verify no invoice created and status untouched
        stmt_inv = select(PlatformInvoice).where(PlatformInvoice.subscription_id == sub.id)
        invoices = (await session.execute(stmt_inv)).scalars().all()
        assert len(invoices) == 0
        await session.refresh(sub)
        assert sub.status == "ACTIVE"


@pytest.mark.asyncio
async def test_roll_single_subscription_cancelled_is_skipped(scheduler_harness):
    """Direct invocation of roll_single_subscription on a CANCELLED subscription is skipped."""
    session_factory, renewal_service, _ = scheduler_harness
    now = _utc_now()

    async with session_factory() as session:
        soc, plan, sub = await _seed_test_tenant(
            session,
            sub_status="CANCELLED",
            auto_renew=False,
            current_period_start=now - timedelta(days=30),
            current_period_end=now,
            next_billing_at=now,
        )
        sub.cancelled_at = now - timedelta(days=10)
        sub.cancellation_reason = "Prior cancellation"
        await session.commit()

        scheduler = BillingPeriodSchedulerService(session, renewal_service=renewal_service)
        roll_res = await scheduler.roll_single_subscription(
            subscription_id=sub.id,
            cutoff_utc=now + timedelta(seconds=1),
            execution_id="test-manual-cancelled",
        )

        assert roll_res.status == "SKIPPED"
        assert roll_res.skip_reason == "SUBSCRIPTION_CANCELLED"
        assert roll_res.invoice_id is None

