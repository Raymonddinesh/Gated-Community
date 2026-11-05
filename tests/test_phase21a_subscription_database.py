"""Phase 21A — Subscription Database Foundation & Isolation Tests."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietyFeatureOverride,
    SocietyProvisioningLog,
    SocietyQuotaOverride,
    SocietySubscription,
    SocietyUsageMetric,
    SubscriptionPlanEntitlement,
)


@pytest.mark.asyncio
async def test_global_subscription_plan_catalog_accessibility(db_session: AsyncSession):
    """Verify global subscription plan creation and entitlement linking."""
    plan = PlatformSubscriptionPlan(
        plan_code="TEST_PRO_PLAN",
        display_name="Test Pro Plan",
        description="Plan for testing",
        monthly_price=999.00,
        annual_price=9990.00,
        currency_code="INR",
        trial_days=14,
        is_active=True,
    )
    db_session.add(plan)
    await db_session.flush()

    entitlement = SubscriptionPlanEntitlement(
        plan_id=plan.id,
        entitlement_key="quota.units.max",
        entitlement_type="NUMERIC",
        entitlement_value="250",
    )
    db_session.add(entitlement)
    await db_session.commit()

    stmt = select(PlatformSubscriptionPlan).options(selectinload(PlatformSubscriptionPlan.entitlements)).where(PlatformSubscriptionPlan.id == plan.id)
    result = await db_session.execute(stmt)
    saved_plan = result.scalar_one_or_none()

    assert saved_plan is not None
    assert saved_plan.plan_code == "TEST_PRO_PLAN"
    assert len(saved_plan.entitlements) == 1
    assert saved_plan.entitlements[0].entitlement_value == "250"


@pytest.mark.asyncio
async def test_duplicate_plan_code_rejected(db_session: AsyncSession):
    """Verify unique constraint on plan_code."""
    plan1 = PlatformSubscriptionPlan(
        plan_code="UNIQUE_PLAN_CODE",
        display_name="Plan One",
        monthly_price=100.00,
    )
    db_session.add(plan1)
    await db_session.commit()

    plan2 = PlatformSubscriptionPlan(
        plan_code="UNIQUE_PLAN_CODE",
        display_name="Plan Two",
        monthly_price=200.00,
    )
    db_session.add(plan2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_invalid_entitlement_type_rejected(db_session: AsyncSession):
    """Verify check constraint on entitlement_type."""
    plan = PlatformSubscriptionPlan(
        plan_code="PLAN_CHECK_TYPE",
        display_name="Check Plan",
        monthly_price=500.00,
    )
    db_session.add(plan)
    await db_session.flush()

    entitlement = SubscriptionPlanEntitlement(
        plan_id=plan.id,
        entitlement_key="feature.invalid",
        entitlement_type="INVALID_TYPE",
        entitlement_value="true",
    )
    db_session.add(entitlement)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_society_subscription_lifecycle_association(db_session: AsyncSession):
    """Verify tenant society association with a subscription plan."""
    society = Society(
        legal_name="Phase 21A Test Society",
        display_name="Phase 21A Society",
        address_line1="123 Test St",
        city="Test City",
        state="Test State",
        postal_code="600001",
    )
    plan = PlatformSubscriptionPlan(
        plan_code="PLAN_SOC_ASSOC",
        display_name="Assoc Plan",
        monthly_price=1500.00,
    )
    db_session.add_all([society, plan])
    await db_session.flush()

    now = datetime.now(UTC).replace(tzinfo=None)
    sub = SocietySubscription(
        society_id=society.id,
        plan_id=plan.id,
        status="TRIAL",
        starts_at=now,
        trial_ends_at=now + timedelta(days=14),
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    db_session.add(sub)
    await db_session.commit()

    saved_sub = await db_session.get(SocietySubscription, sub.id)
    assert saved_sub is not None
    assert saved_sub.society_id == society.id
    assert saved_sub.status == "TRIAL"


@pytest.mark.asyncio
async def test_society_feature_override_uniqueness(db_session: AsyncSession):
    """Verify unique constraint on (society_id, feature_key)."""
    society = Society(
        legal_name="Feature Override Test Society",
        display_name="Feature Override Society",
        address_line1="456 Test Rd",
        city="Test City",
        state="Test State",
        postal_code="600002",
    )
    db_session.add(society)
    await db_session.flush()

    override1 = SocietyFeatureOverride(
        society_id=society.id,
        feature_key="feature.governance",
        is_enabled=True,
        override_reason="Promotional unlock",
    )
    db_session.add(override1)
    await db_session.commit()

    override2 = SocietyFeatureOverride(
        society_id=society.id,
        feature_key="feature.governance",
        is_enabled=False,
        override_reason="Duplicate attempt",
    )
    db_session.add(override2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_society_usage_metric_and_quota_override(db_session: AsyncSession):
    """Verify usage metric counters and quota override limits."""
    society = Society(
        legal_name="Usage Metric Test Society",
        display_name="Usage Metric Society",
        address_line1="789 Metric Ave",
        city="Test City",
        state="Test State",
        postal_code="600003",
    )
    db_session.add(society)
    await db_session.flush()

    metric = SocietyUsageMetric(
        society_id=society.id,
        metric_key="active_units",
        current_value=45,
    )
    quota = SocietyQuotaOverride(
        society_id=society.id,
        quota_key="active_units",
        max_limit=100,
        override_reason="Special approval",
    )
    db_session.add_all([metric, quota])
    await db_session.commit()

    saved_metric = await db_session.get(SocietyUsageMetric, metric.id)
    assert saved_metric is not None
    assert saved_metric.current_value == 45


@pytest.mark.asyncio
async def test_society_provisioning_log_recording(db_session: AsyncSession):
    """Verify provisioning log recording."""
    society = Society(
        legal_name="Provisioning Log Test Society",
        display_name="Provisioning Log Society",
        address_line1="101 Log Way",
        city="Test City",
        state="Test State",
        postal_code="600004",
    )
    db_session.add(society)
    await db_session.flush()

    req_id = uuid.uuid4()
    log = SocietyProvisioningLog(
        society_id=society.id,
        provisioning_request_id=req_id,
        step_key="INITIALIZE_ROLES",
        status="COMPLETED",
        message="Created default roles",
    )
    db_session.add(log)
    await db_session.commit()

    saved_log = await db_session.get(SocietyProvisioningLog, log.id)
    assert saved_log is not None
    assert saved_log.provisioning_request_id == req_id
    assert saved_log.status == "COMPLETED"
