"""Phase 21B — Targeted Usage Reconciliation Concurrency & Safety Tests.

Verifies the 10 targeted reconciliation requirements:
1. Basic reconciliation to the authoritative resource count.
2. Reconciliation when the usage metric row does not exist.
3. Concurrent reservation during reconciliation.
4. Reservation committed after count calculation but before reconciliation.
5. Two concurrent reconciliation attempts.
6. Failed reconciliation rolls back without corrupting usage.
7. A stale reconciliation cannot decrease a newer committed counter.
8. Tenant isolation remains enforced.
9. Reconciliation never creates negative usage.
10. Existing quota reservation ceiling remains enforced.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from apps.api.src.core.exceptions import AuthorizationException, TenantContextRequiredException
from apps.api.src.core.tenant_context import tenant_context
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
    SocietyUsageMetric,
    SubscriptionPlanEntitlement,
)
from apps.api.src.subscriptions.enums import (
    QuotaKey,
    SubscriptionStatus,
)
from apps.api.src.subscriptions.exceptions import (
    InvalidUsageIncrementException,
    QuotaExceededException,
    StaleReconciliationException,
)
from apps.api.src.subscriptions.quota_enforcement_service import QuotaEnforcementService


async def create_society(session: AsyncSession, name: str = "Test Society") -> Society:
    soc = Society(
        legal_name=f"{name} Legal {uuid4().hex[:6]}",
        display_name=name,
        address_line1="123 Palm Ave",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560001",
    )
    session.add(soc)
    await session.flush()
    return soc


async def create_plan(
    session: AsyncSession,
    plan_code: str,
    display_name: str = "Standard Plan",
    is_active: bool = True,
    entitlements: list[dict[str, str]] | None = None,
) -> PlatformSubscriptionPlan:
    plan = PlatformSubscriptionPlan(
        plan_code=plan_code,
        display_name=display_name,
        monthly_price=1999.00,
        annual_price=19990.00,
        currency_code="INR",
        trial_days=14,
        is_active=is_active,
    )
    session.add(plan)
    await session.flush()

    if entitlements:
        for ent in entitlements:
            e = SubscriptionPlanEntitlement(
                plan_id=plan.id,
                entitlement_key=ent["key"],
                entitlement_type=ent.get("type", "NUMERIC"),
                entitlement_value=ent["value"],
            )
            session.add(e)
        await session.flush()
    return plan


async def create_subscription(
    session: AsyncSession,
    society_id: UUID,
    plan_id: UUID,
    status: str = SubscriptionStatus.ACTIVE.value,
    trial_ends_at: datetime | None = None,
) -> SocietySubscription:
    now = datetime.now(UTC).replace(tzinfo=None)
    sub = SocietySubscription(
        society_id=society_id,
        plan_id=plan_id,
        status=status,
        starts_at=now,
        trial_ends_at=trial_ends_at,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    session.add(sub)
    await session.flush()
    return sub


@pytest.mark.asyncio
async def test_01_basic_reconciliation_authoritative_count(db_session: AsyncSession) -> None:
    """1. Basic reconciliation to the authoritative resource count using callback and scalar."""
    soc = await create_society(db_session, "Soc Basic Recon")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_BASIC_RECON",
        entitlements=[{"key": QuotaKey.UNITS_MAX.value, "type": "NUMERIC", "value": "50"}],
    )
    await create_subscription(db_session, soc.id, plan.id)
    await db_session.commit()

    service = QuotaEnforcementService(db_session)
    async with tenant_context(soc.id):
        # Initial usage is 0
        assert await service.get_current_usage(soc.id, QuotaKey.UNITS_MAX.value) == 0

        # In-transaction count callback
        async def count_units_mock(sess: AsyncSession, society_id: UUID) -> int:
            return 12

        val1 = await service.reconcile_usage(
            soc.id, QuotaKey.UNITS_MAX.value, count_callback=count_units_mock
        )
        assert val1 == 12
        assert await service.get_current_usage(soc.id, QuotaKey.UNITS_MAX.value) == 12

        # Coordinated external count reconciliation
        val2 = await service.reconcile_usage(
            soc.id,
            QuotaKey.UNITS_MAX.value,
            actual_count=18,
            expected_previous_value=12,
        )
        assert val2 == 18
        assert await service.get_current_usage(soc.id, QuotaKey.UNITS_MAX.value) == 18


@pytest.mark.asyncio
async def test_02_reconciliation_missing_usage_metric_row(db_session: AsyncSession) -> None:
    """2. Reconciliation safely initializes and updates when usage metric row does not exist."""
    soc = await create_society(db_session, "Soc Missing Metric Recon")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_INIT_RECON",
        entitlements=[{"key": QuotaKey.STAFF_MAX.value, "type": "NUMERIC", "value": "30"}],
    )
    await create_subscription(db_session, soc.id, plan.id)
    await db_session.commit()

    service = QuotaEnforcementService(db_session)
    async with tenant_context(soc.id):
        # Confirm row does not exist in DB yet
        stmt = select(SocietyUsageMetric).where(
            SocietyUsageMetric.society_id == soc.id,
            SocietyUsageMetric.metric_key == QuotaKey.STAFF_MAX.value,
        )
        row_before = (await db_session.execute(stmt)).scalar_one_or_none()
        assert row_before is None

        # Reconcile usage directly on uninitialized row
        val = await service.reconcile_usage(soc.id, QuotaKey.STAFF_MAX.value, actual_count=15)
        assert val == 15

        # Row is now persisted with current_value 15
        row_after = (await db_session.execute(stmt)).scalar_one_or_none()
        assert row_after is not None
        assert row_after.current_value == 15


@pytest.mark.asyncio
async def test_03_concurrent_reservation_during_reconciliation(db_engine: AsyncEngine) -> None:
    """3. Concurrent reservation during reconciliation is serialized via row lock."""
    if db_engine.dialect.name == "sqlite":
        pytest.skip(
            "Row-level lock serialization requires PostgreSQL (SELECT ... FOR UPDATE is a no-op in SQLite)"
        )
    session_maker = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as setup_session:
        soc = await create_society(setup_session, "Soc Recon Lock")
        plan = await create_plan(
            setup_session,
            plan_code="PLAN_LOCK_RECON",
            entitlements=[{"key": QuotaKey.UNITS_MAX.value, "type": "NUMERIC", "value": "50"}],
        )
        await create_subscription(setup_session, soc.id, plan.id)
        # Establish baseline row
        svc = QuotaEnforcementService(setup_session)
        async with tenant_context(soc.id):
            await svc.reserve_usage(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=5)
        await setup_session.commit()
        society_id = soc.id

    recon_started = asyncio.Event()
    reserve_completed = asyncio.Event()

    async def run_reconciliation() -> int:
        async with session_maker() as session:
            service = QuotaEnforcementService(session)
            async with tenant_context(society_id):
                async def counting_callback(sess: AsyncSession, s_id: UUID) -> int:
                    recon_started.set()
                    # Short delay to allow reservation task to start contending for row lock
                    await asyncio.sleep(0.05)
                    return 20

                res = await service.reconcile_usage(
                    society_id,
                    QuotaKey.UNITS_MAX.value,
                    count_callback=counting_callback,
                    auto_commit=True,
                )
                return res

    async def run_reservation() -> None:
        await recon_started.wait()
        async with session_maker() as session:
            service = QuotaEnforcementService(session)
            async with tenant_context(society_id):
                # Will wait for reconciliation transaction to commit or lock release
                await service.reserve_usage(
                    society_id,
                    QuotaKey.UNITS_MAX.value,
                    requested_increment=3,
                    auto_commit=True,
                )
                reserve_completed.set()

    recon_task = asyncio.create_task(run_reconciliation())
    res_task = asyncio.create_task(run_reservation())

    await asyncio.gather(recon_task, res_task)

    # Final count must reflect reconciliation (20) + reservation (+3) = 23
    async with session_maker() as verify_session:
        service = QuotaEnforcementService(verify_session)
        async with tenant_context(society_id):
            final_usage = await service.get_current_usage(society_id, QuotaKey.UNITS_MAX.value)
            assert final_usage == 23


@pytest.mark.asyncio
async def test_04_reservation_committed_after_count_calculation_before_reconciliation(
    db_session: AsyncSession,
) -> None:
    """4. A reservation committed after count calculation prevents stale reconciliation."""
    soc = await create_society(db_session, "Soc Stale Window")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_STALE_WINDOW",
        entitlements=[{"key": QuotaKey.UNITS_MAX.value, "type": "NUMERIC", "value": "50"}],
    )
    await create_subscription(db_session, soc.id, plan.id)
    service = QuotaEnforcementService(db_session)
    async with tenant_context(soc.id):
        # 1. Establish baseline of 10
        await service.reserve_usage(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=10)
    await db_session.commit()

    # 2. Reconciler snapshot is observed when count was 10
    observed_usage = 10
    snapshot_time = datetime.now(UTC).replace(tzinfo=None)

    # 3. In the meantime, user commits a new reservation (+2)
    async with tenant_context(soc.id):
        await service.reserve_usage(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=2)
    await db_session.commit()

    # Current usage in DB is now 12
    async with tenant_context(soc.id):
        assert await service.get_current_usage(soc.id, QuotaKey.UNITS_MAX.value) == 12

        # 4a. Attempt reconciliation with expected_previous_value=10 -> Rejected!
        with pytest.raises(StaleReconciliationException) as exc_info:
            await service.reconcile_usage(
                soc.id,
                QuotaKey.UNITS_MAX.value,
                actual_count=10,
                expected_previous_value=observed_usage,
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.details["current_usage"] == 12

        # 4b. Attempt reconciliation with as_of snapshot time -> Rejected!
        with pytest.raises(StaleReconciliationException):
            await service.reconcile_usage(
                soc.id,
                QuotaKey.UNITS_MAX.value,
                actual_count=10,
                as_of=snapshot_time,
            )

        # 4c. Attempt reconciliation with actual_count=10 uncoordinated -> Rejected!
        with pytest.raises(StaleReconciliationException):
            await service.reconcile_usage(soc.id, QuotaKey.UNITS_MAX.value, actual_count=10)

        # Usage must remain intact at 12
        assert await service.get_current_usage(soc.id, QuotaKey.UNITS_MAX.value) == 12


@pytest.mark.asyncio
async def test_05_two_concurrent_reconciliation_attempts(db_engine: AsyncEngine) -> None:
    """5. Two concurrent reconciliation attempts: lock serializes and stale attempt is rejected."""
    if db_engine.dialect.name == "sqlite":
        pytest.skip(
            "Row-level lock serialization requires PostgreSQL (SELECT ... FOR UPDATE is a no-op in SQLite)"
        )
    session_maker = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as setup_session:
        soc = await create_society(setup_session, "Soc Dual Recon")
        plan = await create_plan(
            setup_session,
            plan_code="PLAN_DUAL_RECON",
            entitlements=[{"key": QuotaKey.UNITS_MAX.value, "type": "NUMERIC", "value": "50"}],
        )
        await create_subscription(setup_session, soc.id, plan.id)
        svc = QuotaEnforcementService(setup_session)
        async with tenant_context(soc.id):
            await svc.reserve_usage(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=5)
        await setup_session.commit()
        society_id = soc.id

    # Worker 1 wants to reconcile to 15 expecting 5
    # Worker 2 wants to reconcile to 20 expecting 5
    async def worker_1() -> str:
        async with session_maker() as session:
            service = QuotaEnforcementService(session)
            async with tenant_context(society_id):
                try:
                    await service.reconcile_usage(
                        society_id,
                        QuotaKey.UNITS_MAX.value,
                        actual_count=15,
                        expected_previous_value=5,
                        auto_commit=True,
                    )
                    return "W1_SUCCESS"
                except StaleReconciliationException:
                    return "W1_STALE"

    async def worker_2() -> str:
        async with session_maker() as session:
            service = QuotaEnforcementService(session)
            async with tenant_context(society_id):
                try:
                    await service.reconcile_usage(
                        society_id,
                        QuotaKey.UNITS_MAX.value,
                        actual_count=20,
                        expected_previous_value=5,
                        auto_commit=True,
                    )
                    return "W2_SUCCESS"
                except StaleReconciliationException:
                    return "W2_STALE"

    res1, res2 = await asyncio.gather(worker_1(), worker_2())

    # Exactly one worker succeeds, the other is rejected as stale
    assert (res1 == "W1_SUCCESS" and res2 == "W2_STALE") or (
        res2 == "W2_SUCCESS" and res1 == "W1_STALE"
    )

    # Counter in database matches the winner
    expected_final = 15 if res1 == "W1_SUCCESS" else 20
    async with session_maker() as verify_session:
        service = QuotaEnforcementService(verify_session)
        async with tenant_context(society_id):
            assert (
                await service.get_current_usage(society_id, QuotaKey.UNITS_MAX.value)
                == expected_final
            )


@pytest.mark.asyncio
async def test_06_failed_reconciliation_rolls_back_without_corrupting_usage(
    db_session: AsyncSession,
) -> None:
    """6. Failed reconciliation rolls back cleanly without corrupting usage counter."""
    soc = await create_society(db_session, "Soc Rollback Recon")
    society_id = soc.id
    plan = await create_plan(
        db_session,
        plan_code="PLAN_RB_RECON",
        entitlements=[{"key": QuotaKey.UNITS_MAX.value, "type": "NUMERIC", "value": "50"}],
    )
    await create_subscription(db_session, society_id, plan.id)
    service = QuotaEnforcementService(db_session)
    async with tenant_context(society_id):
        await service.reserve_usage(society_id, QuotaKey.UNITS_MAX.value, requested_increment=14)
    await db_session.commit()

    async with tenant_context(society_id):
        assert await service.get_current_usage(society_id, QuotaKey.UNITS_MAX.value) == 14

        # Callback raises unexpected exception
        async def failing_callback(sess: AsyncSession, s_id: UUID) -> int:
            raise RuntimeError("Database connection interrupted during resource count")

        with pytest.raises(RuntimeError):
            await service.reconcile_usage(
                society_id, QuotaKey.UNITS_MAX.value, count_callback=failing_callback
            )

        await db_session.rollback()

        # Usage must remain completely intact at 14
        assert await service.get_current_usage(society_id, QuotaKey.UNITS_MAX.value) == 14


@pytest.mark.asyncio
async def test_07_stale_reconciliation_cannot_decrease_newer_committed_counter(
    db_session: AsyncSession,
) -> None:
    """7. An uncoordinated or stale reconciliation attempt cannot decrease a newer committed counter."""
    soc = await create_society(db_session, "Soc No Decrease")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_NO_DEC",
        entitlements=[{"key": QuotaKey.UNITS_MAX.value, "type": "NUMERIC", "value": "50"}],
    )
    await create_subscription(db_session, soc.id, plan.id)
    service = QuotaEnforcementService(db_session)
    async with tenant_context(soc.id):
        # Established usage is 25
        await service.reserve_usage(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=25)
    await db_session.commit()

    async with tenant_context(soc.id):
        # Attempting to decrease usage without coordination raises StaleReconciliationException
        with pytest.raises(StaleReconciliationException) as exc_info:
            await service.reconcile_usage(soc.id, QuotaKey.UNITS_MAX.value, actual_count=20)
        assert exc_info.value.status_code == 409

        # Legitimate decrease WITH expected_previous_value succeeds
        val = await service.reconcile_usage(
            soc.id,
            QuotaKey.UNITS_MAX.value,
            actual_count=20,
            expected_previous_value=25,
        )
        assert val == 20
        assert await service.get_current_usage(soc.id, QuotaKey.UNITS_MAX.value) == 20


@pytest.mark.asyncio
async def test_08_tenant_isolation_remains_enforced(db_session: AsyncSession) -> None:
    """8. Tenant isolation remains strictly enforced for all reconciliation variants."""
    soc_a = await create_society(db_session, "Soc Tenant A")
    soc_b = await create_society(db_session, "Soc Tenant B")
    await db_session.commit()

    service = QuotaEnforcementService(db_session)

    # Cross-tenant rejected
    async with tenant_context(soc_a.id):
        with pytest.raises(AuthorizationException) as exc_info:
            await service.reconcile_usage(soc_b.id, QuotaKey.UNITS_MAX.value, actual_count=10)
        assert exc_info.value.status_code == 403

    # Missing context rejected
    with pytest.raises(TenantContextRequiredException) as exc_info2:
        await service.reconcile_usage(soc_a.id, QuotaKey.UNITS_MAX.value, actual_count=10)
    assert exc_info2.value.status_code == 400


@pytest.mark.asyncio
async def test_09_reconciliation_never_creates_negative_usage(db_session: AsyncSession) -> None:
    """9. Reconciliation strictly rejects negative counts across all invocation forms."""
    soc = await create_society(db_session, "Soc Non Neg Recon")
    await db_session.commit()

    service = QuotaEnforcementService(db_session)
    async with tenant_context(soc.id):
        # Negative scalar
        with pytest.raises(InvalidUsageIncrementException):
            await service.reconcile_usage(soc.id, QuotaKey.UNITS_MAX.value, actual_count=-5)

        # Negative callback return
        async def neg_callback(sess: AsyncSession, s_id: UUID) -> int:
            return -1

        with pytest.raises(InvalidUsageIncrementException):
            await service.reconcile_usage(
                soc.id, QuotaKey.UNITS_MAX.value, count_callback=neg_callback
            )

        # Missing both arguments
        with pytest.raises(InvalidUsageIncrementException):
            await service.reconcile_usage(soc.id, QuotaKey.UNITS_MAX.value)

        # Providing both arguments
        with pytest.raises(InvalidUsageIncrementException):
            await service.reconcile_usage(
                soc.id,
                QuotaKey.UNITS_MAX.value,
                actual_count=10,
                count_callback=neg_callback,
            )


@pytest.mark.asyncio
async def test_10_existing_quota_reservation_ceiling_remains_enforced(
    db_session: AsyncSession,
) -> None:
    """10. Existing quota reservation ceiling remains enforced after reconciliation."""
    soc = await create_society(db_session, "Soc Ceiling After Recon")
    plan = await create_plan(
        db_session,
        plan_code="PLAN_CEIL_RECON",
        entitlements=[{"key": QuotaKey.UNITS_MAX.value, "type": "NUMERIC", "value": "50"}],
    )
    await create_subscription(db_session, soc.id, plan.id)
    await db_session.commit()

    service = QuotaEnforcementService(db_session)
    async with tenant_context(soc.id):
        # Reconcile usage to 48
        val = await service.reconcile_usage(soc.id, QuotaKey.UNITS_MAX.value, actual_count=48)
        assert val == 48

        # Reserve +2 -> Reaches limit exactly 50
        res = await service.reserve_usage(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=2)
        assert res.new_usage == 50
        assert res.previous_usage == 48

        # Reserve +1 -> Exceeds limit
        with pytest.raises(QuotaExceededException) as exc_info:
            await service.reserve_usage(soc.id, QuotaKey.UNITS_MAX.value, requested_increment=1)
        assert exc_info.value.status_code == 409
        assert exc_info.value.details["current_usage"] == 50
        assert exc_info.value.details["requested_increment"] == 1
        assert exc_info.value.details["max_limit"] == 50

        # Diagnostics check
        diag = await service.get_usage_diagnostics(soc.id, QuotaKey.UNITS_MAX.value)
        assert diag.current_value == 50
        assert diag.quota_limit == 50
        assert diag.utilization_percentage == 100.0
