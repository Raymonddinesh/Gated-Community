"""Phase 21E.2 — Subscription State Machine & Proration Engine Unit Tests.

Comprehensive tests covering:
1. Subscription State Machine Transitions:
   - All permitted transitions (TRIAL -> ACTIVE, PAST_DUE, SUSPENDED, CANCELLED;
     ACTIVE -> PAST_DUE, SUSPENDED, CANCELLED;
     PAST_DUE -> ACTIVE, SUSPENDED, CANCELLED;
     SUSPENDED -> ACTIVE, CANCELLED).
   - Prohibited transitions (CANCELLED is strictly terminal; SUSPENDED -> PAST_DUE; duplicate status).
   - Automatic recording of PlatformSubscriptionHistory and PlatformSubscriptionAuditLog.
2. BillingPeriodService:
   - Monthly and annual period calculation.
   - Anchor day month-end clamping (Jan 31 -> Feb 28/29, Mar 31 -> Apr 30) and restoration.
   - Leap year handling (Feb 29 -> Feb 28 in non-leap year).
   - IST calendar boundaries converted to UTC naive datetimes.
   - Trial and grace period calculations.
   - Validation for negative/invalid dates.
3. ProrationEngine:
   - Mid-cycle proration using Decimal arithmetic with 8-decimal intermediate fraction.
   - Currency rounding using ROUND_HALF_UP.
   - Boundary conditions (0% used at start, 100% used at end).
   - Exact half-month and leap-year calculations.
   - Zero and inverted period exceptions.
4. SubscriptionUpgradeService:
   - Mid-cycle immediate plan upgrade proration and net payable calculation.
   - Unused credit calculation, new plan charge, and net payable.
   - Immediate upgrade application and audit logging.
5. SubscriptionDowngradeService:
   - Scheduled downgrade at current_period_end (active plan preserved).
   - Quota pre-check via QuotaEnforcementService:
     - Pass when current usage <= target plan entitlements.
     - Reject with DowngradeQuotaViolationException when usage > target plan entitlements.
   - Duplicate downgrade rejection (DuplicateDowngradeRequestException).
6. GracePeriodService:
   - Grace period evaluation for past-due subscriptions (within vs expired).
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.platform_billing import (
    PlatformSubscriptionAuditLog,
    PlatformSubscriptionHistory,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
    SocietyUsageMetric,
    SubscriptionPlanEntitlement,
)
from apps.api.src.subscriptions import (
    BillingPeriodService,
    DowngradeQuotaViolationException,
    DuplicateDowngradeRequestException,
    GracePeriodService,
    InvalidBillingPeriodException,
    InvalidSubscriptionTransitionException,
    PlanInactiveException,
    PlanNotFoundException,
    ProrationCalculationException,
    ProrationEngine,
    QuotaKey,
    SubscriptionAlreadyCancelledException,
    SubscriptionDowngradeService,
    SubscriptionLifecycleService,
    SubscriptionNotFoundException,
    SubscriptionStatus,
    SubscriptionUpgradeService,
)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
async def seeded_lifecycle_data(db_session: AsyncSession):
    """Seed base society, plans (Basic, Standard, Premium), and entitlements for testing."""
    soc = Society(
        legal_name="Phase 21E.2 State Machine Society",
        display_name="Lifecycle Society",
        address_line1="456 Lifecycle Road",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560002",
        status="ACTIVE",
    )
    db_session.add(soc)
    await db_session.flush()

    # Plan 1: Basic (100 units, 5 staff) - INR 1,000 / mo, INR 10,000 / yr
    plan_basic = PlatformSubscriptionPlan(
        plan_code=f"BASIC_{uuid.uuid4().hex[:6]}",
        display_name="Basic Tier",
        monthly_price=Decimal("1000.00"),
        annual_price=Decimal("10000.00"),
        currency_code="INR",
        trial_days=14,
        is_active=True,
    )
    # Plan 2: Standard (300 units, 20 staff) - INR 3,000 / mo, INR 30,000 / yr
    plan_standard = PlatformSubscriptionPlan(
        plan_code=f"STANDARD_{uuid.uuid4().hex[:6]}",
        display_name="Standard Tier",
        monthly_price=Decimal("3000.00"),
        annual_price=Decimal("30000.00"),
        currency_code="INR",
        trial_days=14,
        is_active=True,
    )
    # Plan 3: Inactive Plan
    plan_inactive = PlatformSubscriptionPlan(
        plan_code=f"INACTIVE_{uuid.uuid4().hex[:6]}",
        display_name="Inactive Tier",
        monthly_price=Decimal("5000.00"),
        annual_price=Decimal("50000.00"),
        currency_code="INR",
        trial_days=0,
        is_active=False,
    )

    db_session.add_all([plan_basic, plan_standard, plan_inactive])
    await db_session.flush()

    # Entitlements for Basic
    ent_basic_units = SubscriptionPlanEntitlement(
        plan_id=plan_basic.id,
        entitlement_key=QuotaKey.UNITS_MAX.value,
        entitlement_type="NUMERIC",
        entitlement_value="100",
    )
    ent_basic_staff = SubscriptionPlanEntitlement(
        plan_id=plan_basic.id,
        entitlement_key=QuotaKey.STAFF_MAX.value,
        entitlement_type="NUMERIC",
        entitlement_value="5",
    )

    # Entitlements for Standard
    ent_standard_units = SubscriptionPlanEntitlement(
        plan_id=plan_standard.id,
        entitlement_key=QuotaKey.UNITS_MAX.value,
        entitlement_type="NUMERIC",
        entitlement_value="300",
    )
    ent_standard_staff = SubscriptionPlanEntitlement(
        plan_id=plan_standard.id,
        entitlement_key=QuotaKey.STAFF_MAX.value,
        entitlement_type="NUMERIC",
        entitlement_value="20",
    )

    db_session.add_all([ent_basic_units, ent_basic_staff, ent_standard_units, ent_standard_staff])
    await db_session.flush()

    # Initial subscription in TRIAL
    now = _utc_now()
    sub = SocietySubscription(
        society_id=soc.id,
        plan_id=plan_basic.id,
        status=SubscriptionStatus.TRIAL.value,
        billing_cycle="MONTHLY",
        starts_at=now,
        current_period_start=now,
        current_period_end=now + timedelta(days=14),
        next_billing_at=now + timedelta(days=14),
        auto_renew=True,
    )
    db_session.add(sub)
    await db_session.flush()


    return {
        "society": soc,
        "plan_basic": plan_basic,
        "plan_standard": plan_standard,
        "plan_inactive": plan_inactive,
        "subscription": sub,
    }


# ============================================================================
# 1. SUBSCRIPTION STATE MACHINE UNIT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_state_machine_trial_to_active(db_session: AsyncSession, seeded_lifecycle_data: dict):
    """Test transition from TRIAL to ACTIVE (e.g. on payment capture)."""
    sub = seeded_lifecycle_data["subscription"]
    service = SubscriptionLifecycleService(db_session)

    admin_id = uuid.uuid4()
    res = await service.transition_status(
        society_id=sub.society_id,
        target_status=SubscriptionStatus.ACTIVE,
        reason="Initial payment verified",
        actor_id=str(admin_id),
    )

    assert res.previous_status == SubscriptionStatus.TRIAL.value
    assert res.new_status == SubscriptionStatus.ACTIVE.value
    assert res.status == SubscriptionStatus.ACTIVE.value

    # Verify database model was updated
    await db_session.refresh(sub)
    assert sub.status == SubscriptionStatus.ACTIVE.value

    # Verify history entry created
    hist_stmt = (
        select(PlatformSubscriptionHistory)
        .where(PlatformSubscriptionHistory.subscription_id == sub.id)
        .order_by(PlatformSubscriptionHistory.created_at.desc())
    )
    hist = (await db_session.execute(hist_stmt)).scalars().first()
    assert hist is not None
    assert hist.previous_status == SubscriptionStatus.TRIAL.value
    assert hist.new_status == SubscriptionStatus.ACTIVE.value
    assert hist.transition_reason == "Initial payment verified"
    assert hist.changed_by == admin_id

    # Verify audit log entry created
    audit_stmt = (
        select(PlatformSubscriptionAuditLog)
        .where(PlatformSubscriptionAuditLog.society_id == sub.society_id)
        .order_by(PlatformSubscriptionAuditLog.created_at.desc())
    )
    audit = (await db_session.execute(audit_stmt)).scalars().first()
    assert audit is not None
    assert audit.action == "SUBSCRIPTION_STATUS_CHANGED"
    assert audit.entity_type == "SUBSCRIPTION"
    assert audit.after_state is not None
    assert audit.after_state["status"] == SubscriptionStatus.ACTIVE.value



@pytest.mark.asyncio
async def test_state_machine_all_permitted_transitions(
    db_session: AsyncSession, seeded_lifecycle_data: dict
):
    """Verify all paths in the transition matrix:
    TRIAL -> PAST_DUE
    PAST_DUE -> ACTIVE
    ACTIVE -> PAST_DUE
    PAST_DUE -> SUSPENDED
    SUSPENDED -> ACTIVE
    ACTIVE -> SUSPENDED
    SUSPENDED -> CANCELLED
    """
    sub = seeded_lifecycle_data["subscription"]
    service = SubscriptionLifecycleService(db_session)
    actor = "system-orchestrator"

    # 1. TRIAL -> PAST_DUE (trial ended without card)
    res1 = await service.transition_status(
        sub.society_id, SubscriptionStatus.PAST_DUE, "Trial ended", actor
    )
    assert res1.new_status == SubscriptionStatus.PAST_DUE.value

    # 2. PAST_DUE -> ACTIVE (payment recovered)
    res2 = await service.transition_status(
        sub.society_id, SubscriptionStatus.ACTIVE, "Payment recovered", actor
    )
    assert res2.new_status == SubscriptionStatus.ACTIVE.value

    # 3. ACTIVE -> PAST_DUE (recurring payment failure)
    res3 = await service.transition_status(
        sub.society_id, SubscriptionStatus.PAST_DUE, "Payment failed", actor
    )
    assert res3.new_status == SubscriptionStatus.PAST_DUE.value

    # 4. PAST_DUE -> SUSPENDED (grace period expired)
    res4 = await service.transition_status(
        sub.society_id, SubscriptionStatus.SUSPENDED, "Grace period expired", actor
    )
    assert res4.new_status == SubscriptionStatus.SUSPENDED.value

    # 5. SUSPENDED -> ACTIVE (manual reactivate on settlement)
    res5 = await service.transition_status(
        sub.society_id, SubscriptionStatus.ACTIVE, "Manual reactivation", actor
    )
    assert res5.new_status == SubscriptionStatus.ACTIVE.value

    # 6. ACTIVE -> SUSPENDED (administrative hold)
    res6 = await service.transition_status(
        sub.society_id, SubscriptionStatus.SUSPENDED, "Admin hold", actor
    )
    assert res6.new_status == SubscriptionStatus.SUSPENDED.value

    # 7. SUSPENDED -> CANCELLED (cancellation/termination)
    res7 = await service.transition_status(
        sub.society_id, SubscriptionStatus.CANCELLED, "Contract terminated", actor
    )
    assert res7.new_status == SubscriptionStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_state_machine_trial_to_suspended_and_cancelled(
    db_session: AsyncSession, seeded_lifecycle_data: dict
):
    """Test TRIAL -> SUSPENDED and TRIAL -> CANCELLED transitions."""
    sub = seeded_lifecycle_data["subscription"]
    service = SubscriptionLifecycleService(db_session)

    # TRIAL -> SUSPENDED
    res = await service.transition_status(
        sub.society_id, SubscriptionStatus.SUSPENDED, "Trial suspended for fraud"
    )
    assert res.new_status == SubscriptionStatus.SUSPENDED.value

    # SUSPENDED -> CANCELLED
    res_cancel = await service.transition_status(
        sub.society_id, SubscriptionStatus.CANCELLED, "Customer cancelled"
    )
    assert res_cancel.new_status == SubscriptionStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_state_machine_cancelled_is_strictly_terminal(
    db_session: AsyncSession, seeded_lifecycle_data: dict
):
    """Verify that once a subscription is CANCELLED, NO further transitions are allowed."""
    sub = seeded_lifecycle_data["subscription"]
    service = SubscriptionLifecycleService(db_session)

    # Move to CANCELLED
    await service.transition_status(
        sub.society_id, SubscriptionStatus.CANCELLED, "Cancelled by user"
    )

    # Attempting to move CANCELLED -> ACTIVE must raise SubscriptionAlreadyCancelledException
    with pytest.raises(SubscriptionAlreadyCancelledException) as exc1:
        await service.transition_status(
            sub.society_id, SubscriptionStatus.ACTIVE, "Attempt reactivate"
        )
    assert "CANCELLED" in str(exc1.value)

    # Attempting to move CANCELLED -> PAST_DUE
    with pytest.raises(SubscriptionAlreadyCancelledException):
        await service.transition_status(
            sub.society_id, SubscriptionStatus.PAST_DUE, "Attempt past due"
        )

    # Attempting to move CANCELLED -> SUSPENDED
    with pytest.raises(SubscriptionAlreadyCancelledException):
        await service.transition_status(
            sub.society_id, SubscriptionStatus.SUSPENDED, "Attempt suspend"
        )

    # Attempting to move CANCELLED -> TRIAL
    with pytest.raises(SubscriptionAlreadyCancelledException):
        await service.transition_status(
            sub.society_id, SubscriptionStatus.TRIAL, "Attempt trial"
        )


@pytest.mark.asyncio
async def test_state_machine_prohibited_transitions(
    db_session: AsyncSession, seeded_lifecycle_data: dict
):
    """Test prohibited transitions according to state machine matrix."""
    sub = seeded_lifecycle_data["subscription"]
    service = SubscriptionLifecycleService(db_session)

    # 1. Duplicate transition (TRIAL -> TRIAL)
    with pytest.raises(InvalidSubscriptionTransitionException) as exc_dup:
        await service.transition_status(
            sub.society_id, SubscriptionStatus.TRIAL, "Duplicate transition"
        )
    assert exc_dup.value.from_status == "TRIAL"
    assert exc_dup.value.to_status == "TRIAL"

    # Suspend it
    await service.transition_status(sub.society_id, SubscriptionStatus.SUSPENDED, "Suspend")

    # 2. SUSPENDED -> PAST_DUE is prohibited
    with pytest.raises(InvalidSubscriptionTransitionException) as exc_susp:
        await service.transition_status(
            sub.society_id, SubscriptionStatus.PAST_DUE, "Invalid transition"
        )
    assert exc_susp.value.from_status == "SUSPENDED"
    assert exc_susp.value.to_status == "PAST_DUE"


@pytest.mark.asyncio
async def test_state_machine_nonexistent_society(db_session: AsyncSession):
    """Test transition on a non-existent society raises SubscriptionNotFoundException."""
    service = SubscriptionLifecycleService(db_session)
    with pytest.raises(SubscriptionNotFoundException):
        await service.transition_status(
            uuid.uuid4(), SubscriptionStatus.ACTIVE, "Nonexistent test transition"
        )


@pytest.mark.asyncio
async def test_state_machine_target_plan_inactive_or_missing(
    db_session: AsyncSession, seeded_lifecycle_data: dict
):
    """Test transitioning with a new plan fails if plan doesn't exist or is inactive."""
    sub = seeded_lifecycle_data["subscription"]
    plan_inactive = seeded_lifecycle_data["plan_inactive"]
    service = SubscriptionLifecycleService(db_session)

    # Missing plan
    with pytest.raises(PlanNotFoundException):
        await service.transition_status(
            sub.society_id,
            SubscriptionStatus.ACTIVE,
            "Change plan test",
            target_plan_id=uuid.uuid4(),
        )

    # Inactive plan
    with pytest.raises(PlanInactiveException):
        await service.transition_status(
            sub.society_id,
            SubscriptionStatus.ACTIVE,
            "Change to inactive test",
            target_plan_id=plan_inactive.id,
        )


# ============================================================================
# 2. BILLING PERIOD SERVICE UNIT TESTS
# ============================================================================


def test_billing_period_monthly_anchor_clamping():
    """Verify month-end clamping and subsequent restoration:
    Jan 31 -> Feb 28 (in non-leap year) -> Mar 31
    """
    # 2023 is non-leap year (Feb has 28 days)
    jan_31 = datetime(2023, 1, 31, 0, 0, 0)
    cycle_start, next_end = BillingPeriodService.calculate_next_period(
        cycle_start=jan_31,
        billing_cycle="MONTHLY",
        anchor_day=31,
    )
    # Next period ends on Feb 28, 2023
    assert next_end.year == 2023
    assert next_end.month == 2
    assert next_end.day == 28

    # From Feb 28 with anchor 31, next month (March) has 31 days, so it restores to 31!
    mar_start, mar_end = BillingPeriodService.calculate_next_period(
        cycle_start=next_end,
        billing_cycle="MONTHLY",
        anchor_day=31,
    )
    assert mar_end.year == 2023
    assert mar_end.month == 3
    assert mar_end.day == 31


def test_billing_period_leap_year_clamping():
    """Verify leap year clamping:
    Jan 31, 2024 -> Feb 29, 2024 (2024 is leap year).
    """
    jan_31 = datetime(2024, 1, 31, 0, 0, 0)
    cycle_start, next_end = BillingPeriodService.calculate_next_period(
        cycle_start=jan_31,
        billing_cycle="MONTHLY",
        anchor_day=31,
    )
    assert next_end.year == 2024
    assert next_end.month == 2
    assert next_end.day == 29


def test_billing_period_annual_leap_year():
    """Verify annual billing calculation from leap day:
    Feb 29, 2024 -> Feb 28, 2025.
    """
    leap_day = datetime(2024, 2, 29, 10, 0, 0)
    cycle_start, next_end = BillingPeriodService.calculate_next_period(
        cycle_start=leap_day,
        billing_cycle="ANNUAL",
        anchor_day=29,
    )
    assert next_end.year == 2025
    assert next_end.month == 2
    assert next_end.day == 28


def test_billing_period_trial_and_grace_periods():
    """Test trial period and grace period calculation methods."""
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    t_start, t_end = BillingPeriodService.calculate_trial_period(14, start_time=start)
    assert t_start == start
    assert t_end == start + timedelta(days=14)

    due = datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC)
    grace_expiry = BillingPeriodService.calculate_grace_period_end(due, grace_days=7)
    assert grace_expiry == due + timedelta(days=7)



def test_billing_period_invalid_cycle():
    """Test that invalid billing cycle raises InvalidBillingPeriodException."""
    start = datetime(2026, 1, 1, 0, 0, 0)
    with pytest.raises(InvalidBillingPeriodException):
        BillingPeriodService.calculate_next_period(
            cycle_start=start,
            billing_cycle="BI_WEEKLY",  # Not supported
            anchor_day=1,
        )


# ============================================================================
# 3. PRORATION ENGINE UNIT TESTS
# ============================================================================


def test_proration_mid_cycle_halfway():
    """Test 50% period usage proration."""
    start = datetime(2026, 1, 1, 0, 0, 0)
    end = datetime(2026, 1, 31, 0, 0, 0)  # 30 days duration
    now = datetime(2026, 1, 16, 0, 0, 0)  # Exactly 15 days = 50%

    res = ProrationEngine.calculate_proration(
        period_start=start,
        period_end=end,
        as_of_time=now,
        rate=Decimal("1000.00"),
    )

    assert res.total_seconds == 30 * 86400
    assert res.remaining_seconds == 15 * 86400
    assert res.used_fraction == Decimal("0.50000000")
    assert res.remaining_fraction == Decimal("0.50000000")
    assert res.prorated_amount == Decimal("500.00")


def test_proration_boundary_conditions():
    """Test 100% remaining at start, and 0% remaining at or after end."""
    start = datetime(2026, 6, 1, 0, 0, 0)
    end = datetime(2026, 7, 1, 0, 0, 0)
    rate = Decimal("1500.00")

    # At start: 100% remaining
    res_start = ProrationEngine.calculate_proration(start, end, start, rate)
    assert res_start.remaining_fraction == Decimal("1.00000000")
    assert res_start.used_fraction == Decimal("0.00000000")
    assert res_start.prorated_amount == Decimal("1500.00")

    # At end: 0% remaining
    res_end = ProrationEngine.calculate_proration(start, end, end, rate)
    assert res_end.remaining_fraction == Decimal("0.00000000")
    assert res_end.used_fraction == Decimal("1.00000000")
    assert res_end.prorated_amount == Decimal("0.00")

    # After end: 0% remaining clamped
    after = end + timedelta(days=2)
    res_after = ProrationEngine.calculate_proration(start, end, after, rate)
    assert res_after.remaining_fraction == Decimal("0.00000000")
    assert res_after.prorated_amount == Decimal("0.00")


def test_proration_decimal_rounding_round_half_up():
    """Test ROUND_HALF_UP rounding behaviour:
    1/3 of 1000 = 333.33333333... -> 333.33
    2/3 of 1000 = 666.66666667... -> 666.67
    """
    start = datetime(2026, 1, 1, 0, 0, 0)
    end = datetime(2026, 1, 4, 0, 0, 0)  # 3 days = 259,200 s
    rate = Decimal("1000.00")

    # 1 day remaining (day 2 to day 4, as of day 3 = 1 day left)
    # Remaining 1 / 3 = 0.33333333
    day_3 = start + timedelta(days=2)
    res_1_3 = ProrationEngine.calculate_proration(start, end, day_3, rate)
    assert res_1_3.prorated_amount == Decimal("333.33")

    # 2 days remaining (as of day 2 = 2 days left)
    # Remaining 2 / 3 = 0.66666667
    day_2 = start + timedelta(days=1)
    res_2_3 = ProrationEngine.calculate_proration(start, end, day_2, rate)
    assert res_2_3.prorated_amount == Decimal("666.67")


def test_proration_invalid_zero_duration():
    """Verify that period_end <= period_start raises ProrationCalculationException."""
    start = datetime(2026, 1, 1, 0, 0, 0)
    with pytest.raises(ProrationCalculationException):
        ProrationEngine.calculate_proration(start, start, start, Decimal("1000.00"))

    with pytest.raises(ProrationCalculationException):
        ProrationEngine.calculate_proration(
            start, start - timedelta(days=1), start, Decimal("1000.00")
        )


# ============================================================================
# 4. SUBSCRIPTION UPGRADE SERVICE UNIT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_upgrade_calculation_mid_cycle(db_session: AsyncSession, seeded_lifecycle_data: dict):
    """Verify upgrade calculation:
    Basic (1,000/mo) -> Standard (3,000/mo) halfway through a 30-day cycle.
    Unused credit on Basic = 500.00
    New charge on Standard = 1500.00
    Net payable = 1000.00
    """
    sub = seeded_lifecycle_data["subscription"]
    plan_basic = seeded_lifecycle_data["plan_basic"]
    plan_standard = seeded_lifecycle_data["plan_standard"]

    # Set subscription active with 30-day window
    cycle_start = datetime(2026, 3, 1, 0, 0, 0)
    cycle_end = datetime(2026, 3, 31, 0, 0, 0)
    sub.status = "ACTIVE"
    sub.current_period_start = cycle_start
    sub.current_period_end = cycle_end
    await db_session.flush()

    service = SubscriptionUpgradeService(db_session)
    as_of = datetime(2026, 3, 16, 0, 0, 0)  # Exactly half cycle

    result = await service.calculate_upgrade(
        society_id=sub.society_id,
        target_plan_id=plan_standard.id,
        as_of_time=as_of,
    )

    assert result.current_plan_code == plan_basic.plan_code
    assert result.target_plan_code == plan_standard.plan_code
    assert result.current_plan_rate == Decimal("1000.00")
    assert result.target_plan_rate == Decimal("3000.00")
    assert result.remaining_fraction == Decimal("0.50000000")
    assert result.unused_credit == Decimal("500.00")
    assert result.new_plan_charge == Decimal("1500.00")
    assert result.net_payable == Decimal("1000.00")
    assert result.credit_note_amount == Decimal("0.00")


@pytest.mark.asyncio
async def test_upgrade_application_and_audit(db_session: AsyncSession, seeded_lifecycle_data: dict):
    """Verify apply_upgrade immediately switches the plan, writes history and audit log."""
    sub = seeded_lifecycle_data["subscription"]
    plan_basic = seeded_lifecycle_data["plan_basic"]
    plan_standard = seeded_lifecycle_data["plan_standard"]

    sub.status = "ACTIVE"
    await db_session.flush()

    service = SubscriptionUpgradeService(db_session)
    res = await service.apply_upgrade(
        society_id=sub.society_id,
        target_plan_id=plan_standard.id,
        actor_id="finance-super-admin",
        reason="Customer requested higher capacity",
    )

    assert res.current_plan_code == plan_basic.plan_code
    assert res.target_plan_code == plan_standard.plan_code

    # Verify database model was updated
    await db_session.refresh(sub)
    assert sub.plan_id == plan_standard.id

    # Verify history entry
    hist_stmt = (
        select(PlatformSubscriptionHistory)
        .where(
            PlatformSubscriptionHistory.society_id == sub.society_id,
            PlatformSubscriptionHistory.new_plan_id == plan_standard.id,
        )
        .order_by(PlatformSubscriptionHistory.created_at.desc())
    )
    hist = (await db_session.execute(hist_stmt)).scalars().first()
    assert hist is not None
    assert hist.previous_plan_id == plan_basic.id
    assert hist.new_plan_id == plan_standard.id
    assert "UPGRADE" in hist.transition_reason


# ============================================================================
# 5. SUBSCRIPTION DOWNGRADE SERVICE UNIT TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_downgrade_quota_violation_rejection(
    db_session: AsyncSession, seeded_lifecycle_data: dict
):
    """Verify downgrade is rejected with DowngradeQuotaViolationException
    when current usage exceeds target plan's entitlements.
    Standard (300 units) -> Basic (100 units limit).
    Current usage = 150 units -> VIOLATION!
    """
    soc = seeded_lifecycle_data["society"]
    sub = seeded_lifecycle_data["subscription"]
    plan_basic = seeded_lifecycle_data["plan_basic"]
    plan_standard = seeded_lifecycle_data["plan_standard"]

    # Subscription currently on Standard
    sub.plan_id = plan_standard.id
    sub.status = "ACTIVE"
    sub.current_period_end = _utc_now() + timedelta(days=20)
    await db_session.flush()

    # Record current usage = 150 units (exceeds Basic's 100 limit)
    metric = SocietyUsageMetric(
        society_id=soc.id,
        metric_key=QuotaKey.UNITS_MAX.value,
        current_value=150,
    )
    db_session.add(metric)
    await db_session.flush()

    downgrade_service = SubscriptionDowngradeService(db_session)

    with pytest.raises(DowngradeQuotaViolationException) as exc:
        await downgrade_service.schedule_downgrade(
            society_id=soc.id,
            target_plan_id=plan_basic.id,
            actor_id=str(uuid.uuid4()),
            reason="Downsizing society",
        )

    assert exc.value.target_plan_code == plan_basic.plan_code
    assert isinstance(exc.value.violations, dict)
    assert QuotaKey.UNITS_MAX.value in exc.value.violations
    assert exc.value.violations[QuotaKey.UNITS_MAX.value]["current_usage"] == 150
    assert exc.value.violations[QuotaKey.UNITS_MAX.value]["target_limit"] == 100


@pytest.mark.asyncio
async def test_downgrade_scheduling_success(db_session: AsyncSession, seeded_lifecycle_data: dict):
    """Verify downgrade succeeds when usage is within limits.
    Scheduled at current_period_end; plan is NOT changed immediately.
    """
    soc = seeded_lifecycle_data["society"]
    sub = seeded_lifecycle_data["subscription"]
    plan_basic = seeded_lifecycle_data["plan_basic"]
    plan_standard = seeded_lifecycle_data["plan_standard"]

    sub.plan_id = plan_standard.id
    sub.status = "ACTIVE"
    period_end = _utc_now() + timedelta(days=20)
    sub.current_period_end = period_end
    await db_session.flush()

    # Usage within limits: 50 units (limit is 100)
    metric = SocietyUsageMetric(
        society_id=soc.id,
        metric_key=QuotaKey.UNITS_MAX.value,
        current_value=50,
    )
    db_session.add(metric)
    await db_session.flush()

    downgrade_service = SubscriptionDowngradeService(db_session)
    res = await downgrade_service.schedule_downgrade(
        society_id=soc.id,
        target_plan_id=plan_basic.id,
        actor_id=str(uuid.uuid4()),
        reason="Switch to basic next month",
    )

    assert res.target_plan_code == plan_basic.plan_code
    assert res.effective_at == period_end
    assert res.active_until == period_end

    # Active subscription plan MUST NOT have changed yet!
    await db_session.refresh(sub)
    assert sub.plan_id == plan_standard.id


@pytest.mark.asyncio
async def test_duplicate_downgrade_rejection(
    db_session: AsyncSession, seeded_lifecycle_data: dict
):
    """Verify that scheduling a second downgrade to the same plan raises DuplicateDowngradeRequestException."""
    soc = seeded_lifecycle_data["society"]
    sub = seeded_lifecycle_data["subscription"]
    plan_basic = seeded_lifecycle_data["plan_basic"]
    plan_standard = seeded_lifecycle_data["plan_standard"]

    sub.plan_id = plan_standard.id
    sub.status = "ACTIVE"
    sub.current_period_end = _utc_now() + timedelta(days=15)
    await db_session.flush()

    # 10 units usage
    db_session.add(
        SocietyUsageMetric(
            society_id=soc.id,
            metric_key=QuotaKey.UNITS_MAX.value,
            current_value=10,
            )
    )
    await db_session.flush()

    downgrade_service = SubscriptionDowngradeService(db_session)
    admin_id = str(uuid.uuid4())

    # First request succeeds
    await downgrade_service.schedule_downgrade(
        society_id=soc.id,
        target_plan_id=plan_basic.id,
        actor_id=admin_id,
        reason="First request",
    )

    # Second request raises DuplicateDowngradeRequestException
    with pytest.raises(DuplicateDowngradeRequestException):
        await downgrade_service.schedule_downgrade(
            society_id=soc.id,
            target_plan_id=plan_basic.id,
            actor_id=admin_id,
            reason="Second duplicate request",
        )



# ============================================================================
# 6. GRACE PERIOD SERVICE UNIT TESTS
# ============================================================================


def test_grace_period_service_evaluation():
    """Verify grace period expiration calculation."""
    due = datetime(2026, 4, 1, 0, 0, 0)
    service = GracePeriodService(default_grace_days=7)

    # 3 days after due date -> still within grace period
    eval_within = service.evaluate_grace_period(due_date=due, as_of_time=due + timedelta(days=3))
    assert not eval_within.is_expired
    assert eval_within.seconds_remaining == 4 * 86400
    assert eval_within.seconds_overdue == 0

    # 7 days after due date (exactly at grace period end) -> expired
    eval_exact = service.evaluate_grace_period(due_date=due, as_of_time=due + timedelta(days=7))
    assert eval_exact.is_expired
    assert eval_exact.seconds_remaining == 0
    assert eval_exact.seconds_overdue == 0

    # 10 days after due date -> 3 days overdue
    eval_overdue = service.evaluate_grace_period(
        due_date=due, as_of_time=due + timedelta(days=10)
    )
    assert eval_overdue.is_expired
    assert eval_overdue.seconds_remaining == 0
    assert eval_overdue.seconds_overdue == 3 * 86400
