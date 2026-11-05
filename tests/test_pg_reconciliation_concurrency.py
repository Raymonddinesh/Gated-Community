"""Live PostgreSQL 16 Concurrency and Reconciliation Race Tests.

Executes genuine concurrent multi-session tests against PostgreSQL 16
(societysphere-postgres on localhost:5432) using explicit asyncio barriers.
"""

import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.src.core.tenant_context import tenant_context
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
    SubscriptionPlanEntitlement,
)
from apps.api.src.subscriptions.enums import (
    QuotaKey,
    SubscriptionStatus,
)
from apps.api.src.subscriptions.exceptions import (
    QuotaExceededException,
    StaleReconciliationException,
)
from apps.api.src.subscriptions.quota_enforcement_service import QuotaEnforcementService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pg_concurrency_test")

PG_URL = "postgresql+asyncpg://postgres:postgrespassword@localhost:5432/societysphere_dev"


@pytest_asyncio.fixture
async def engine():
    try:
        eng = create_async_engine(PG_URL, echo=False)
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL 16 is not accessible at localhost:5432")
    yield eng
    await eng.dispose()



async def setup_test_society_and_plan(
    session: AsyncSession,
    plan_code: str,
    quota_limit: int,
) -> tuple[Society, PlatformSubscriptionPlan, SocietySubscription]:
    soc = Society(
        legal_name=f"PG Concurrency Society {uuid4().hex[:6]}",
        display_name="PG Concurrency Society",
        address_line1="100 Tech Park",
        city="Bengaluru",
        state="Karnataka",
        postal_code="560100",
    )
    session.add(soc)
    await session.flush()

    plan = PlatformSubscriptionPlan(
        plan_code=plan_code,
        display_name=f"PG Test Plan {plan_code}",
        monthly_price=5000.0,
        annual_price=50000.0,
        currency_code="INR",
        trial_days=14,
        is_active=True,
    )
    session.add(plan)
    await session.flush()

    ent = SubscriptionPlanEntitlement(
        plan_id=plan.id,
        entitlement_key=QuotaKey.UNITS_MAX.value,
        entitlement_type="NUMERIC",
        entitlement_value=str(quota_limit),
    )
    session.add(ent)
    await session.flush()

    now = datetime.now(UTC).replace(tzinfo=None)
    sub = SocietySubscription(
        society_id=soc.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE.value,
        starts_at=now,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    session.add(sub)
    await session.flush()
    await session.commit()

    return soc, plan, sub


@pytest.mark.asyncio
async def test_pg_concurrent_reservation_during_reconciliation(engine) -> None:
    """Test 1: In-transaction reconciliation holding row lock blocks concurrent reservation."""
    logger.info("--- Starting Test 1: PostgreSQL Row Lock Serialization ---")
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        soc, plan, sub = await setup_test_society_and_plan(session, f"PG_P1_{uuid4().hex[:4]}", 50)
        society_id = soc.id
        # Establish baseline = 5
        svc = QuotaEnforcementService(session)
        async with tenant_context(society_id):
            await svc.reserve_usage(society_id, QuotaKey.UNITS_MAX.value, requested_increment=5, auto_commit=True)

    lock_acquired_event = asyncio.Event()
    recon_committed_event = asyncio.Event()

    async def session_a_reconcile():
        async with session_maker() as session:
            svc = QuotaEnforcementService(session)
            async with tenant_context(society_id):
                async def counting_callback(sess: AsyncSession, s_id: UUID) -> int:
                    logger.info("Session A: holding row lock inside callback")
                    lock_acquired_event.set()
                    # Sleep 300ms to allow Session B to attempt reservation while lock is held
                    await asyncio.sleep(0.3)
                    logger.info("Session A: finished counting, returning 20")
                    return 20

                val = await svc.reconcile_usage(
                    society_id,
                    QuotaKey.UNITS_MAX.value,
                    count_callback=counting_callback,
                    auto_commit=True,
                )
                recon_committed_event.set()
                logger.info(f"Session A: committed reconciliation to {val}")

    async def session_b_reserve():
        # Wait until Session A has acquired the row lock
        await lock_acquired_event.wait()
        logger.info("Session B: attempting reserve_usage while Session A holds lock...")
        start_time = asyncio.get_event_loop().time()
        async with session_maker() as session:
            svc = QuotaEnforcementService(session)
            async with tenant_context(society_id):
                res = await svc.reserve_usage(
                    society_id,
                    QuotaKey.UNITS_MAX.value,
                    requested_increment=3,
                    auto_commit=True,
                )
                elapsed = asyncio.get_event_loop().time() - start_time
                logger.info(f"Session B: reservation succeeded after waiting {elapsed:.3f}s, new usage={res.new_usage}")
                assert recon_committed_event.is_set(), "Session B must have waited until Session A committed!"
                assert res.previous_usage == 20, f"Session B must see reconciled count 20, got {res.previous_usage}"
                assert res.new_usage == 23, f"Session B new usage must be 23, got {res.new_usage}"

    await asyncio.gather(session_a_reconcile(), session_b_reserve())

    # Verify final usage in fresh session
    async with session_maker() as session:
        svc = QuotaEnforcementService(session)
        async with tenant_context(society_id):
            final = await svc.get_current_usage(society_id, QuotaKey.UNITS_MAX.value)
            logger.info(f"Test 1 PASSED: Final usage in PostgreSQL is {final} (Expected: 23)")
            assert final == 23


@pytest.mark.asyncio
async def test_pg_two_concurrent_reconciliations(engine) -> None:
    """Test 2: Two concurrent reconciliation attempts with expected_previous_value."""
    logger.info("--- Starting Test 2: Two Concurrent Reconciliations ---")
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        soc, plan, sub = await setup_test_society_and_plan(session, f"PG_P2_{uuid4().hex[:4]}", 50)
        society_id = soc.id
        svc = QuotaEnforcementService(session)
        async with tenant_context(society_id):
            await svc.reserve_usage(society_id, QuotaKey.UNITS_MAX.value, requested_increment=5, auto_commit=True)

    async def worker(worker_id: int, target_count: int) -> str:
        async with session_maker() as session:
            svc = QuotaEnforcementService(session)
            async with tenant_context(society_id):
                try:
                    await svc.reconcile_usage(
                        society_id,
                        QuotaKey.UNITS_MAX.value,
                        actual_count=target_count,
                        expected_previous_value=5,
                        auto_commit=True,
                    )
                    return f"W{worker_id}_SUCCESS"
                except StaleReconciliationException:
                    return f"W{worker_id}_STALE"

    res1, res2 = await asyncio.gather(worker(1, 15), worker(2, 20))
    logger.info(f"Test 2 results: {res1}, {res2}")
    assert (res1 == "W1_SUCCESS" and res2 == "W2_STALE") or (res2 == "W2_SUCCESS" and res1 == "W1_STALE")

    async with session_maker() as session:
        svc = QuotaEnforcementService(session)
        async with tenant_context(society_id):
            final = await svc.get_current_usage(society_id, QuotaKey.UNITS_MAX.value)
            expected = 15 if res1 == "W1_SUCCESS" else 20
            logger.info(f"Test 2 PASSED: Final usage in PostgreSQL is {final} (Expected: {expected})")
            assert final == expected


@pytest.mark.asyncio
async def test_pg_reservation_committed_after_count_before_reconcile(engine) -> None:
    """Test 3: Reservation committed after count calculation prevents stale overwrite."""
    logger.info("--- Starting Test 3: Stale Overwrite Prevention ---")
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        soc, plan, sub = await setup_test_society_and_plan(session, f"PG_P3_{uuid4().hex[:4]}", 50)
        society_id = soc.id
        svc = QuotaEnforcementService(session)
        async with tenant_context(society_id):
            await svc.reserve_usage(society_id, QuotaKey.UNITS_MAX.value, requested_increment=10, auto_commit=True)

    # Reconciler observed count 10 at snapshot_time
    observed_count = 10
    snapshot_time = datetime.now(UTC).replace(tzinfo=None)

    # User reservation commits +2 in between
    async with session_maker() as session:
        svc = QuotaEnforcementService(session)
        async with tenant_context(society_id):
            await svc.reserve_usage(society_id, QuotaKey.UNITS_MAX.value, requested_increment=2, auto_commit=True)

    # Reconciler attempts reconciliation
    async with session_maker() as session:
        svc = QuotaEnforcementService(session)
        async with tenant_context(society_id):
            current = await svc.get_current_usage(society_id, QuotaKey.UNITS_MAX.value)
            assert current == 12

            # Attempt with expected_previous_value=10
            rejected_1 = False
            try:
                await svc.reconcile_usage(
                    society_id,
                    QuotaKey.UNITS_MAX.value,
                    actual_count=10,
                    expected_previous_value=observed_count,
                )
            except StaleReconciliationException:
                rejected_1 = True
            assert rejected_1, "Expected StaleReconciliationException when expected_previous_value mismatches!"

            # Attempt with as_of snapshot time
            rejected_2 = False
            try:
                await svc.reconcile_usage(
                    society_id,
                    QuotaKey.UNITS_MAX.value,
                    actual_count=10,
                    as_of=snapshot_time,
                )
            except StaleReconciliationException:
                rejected_2 = True
            assert rejected_2, "Expected StaleReconciliationException when as_of is older than last_calculated_at!"

            # Attempt uncoordinated actual_count=10 (cannot decrease 12 to 10)
            rejected_3 = False
            try:
                await svc.reconcile_usage(society_id, QuotaKey.UNITS_MAX.value, actual_count=10)
            except StaleReconciliationException:
                rejected_3 = True
            assert rejected_3, "Expected StaleReconciliationException when uncoordinated count decreases usage!"

            # Final check: PostgreSQL usage remains intact at 12
            final = await svc.get_current_usage(society_id, QuotaKey.UNITS_MAX.value)
            logger.info(f"Test 3 PASSED: Final usage in PostgreSQL is preserved at {final} (Expected: 12)")
            assert final == 12


@pytest.mark.asyncio
async def test_pg_check1_concurrency_regression(engine) -> None:
    """Test 4: Check 1 regression: 10 concurrent workers competing for 5 units."""
    logger.info("--- Starting Test 4: Check 1 Quota Concurrency Regression ---")
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        soc, plan, sub = await setup_test_society_and_plan(session, f"PG_P4_{uuid4().hex[:4]}", 5)
        society_id = soc.id

    async def worker(worker_id: int) -> bool:
        async with session_maker() as session:
            svc = QuotaEnforcementService(session)
            async with tenant_context(society_id):
                try:
                    await svc.reserve_usage(
                        society_id,
                        QuotaKey.UNITS_MAX.value,
                        requested_increment=1,
                        auto_commit=True,
                    )
                    return True
                except QuotaExceededException:
                    return False

    results = await asyncio.gather(*(worker(i) for i in range(10)))
    success_count = sum(1 for r in results if r is True)
    logger.info(f"Test 4 results: {success_count} succeeded, {10 - success_count} rejected")
    assert success_count == 5, f"Exactly 5 workers must succeed, got {success_count}"

    async with session_maker() as session:
        svc = QuotaEnforcementService(session)
        async with tenant_context(society_id):
            final = await svc.get_current_usage(society_id, QuotaKey.UNITS_MAX.value)
            logger.info(f"Test 4 PASSED: Final usage in PostgreSQL is {final} (Expected: 5)")
            assert final == 5


async def main() -> None:
    engine = create_async_engine(PG_URL, echo=False)
    try:
        await test_pg_concurrent_reservation_during_reconciliation(engine)
        await test_pg_two_concurrent_reconciliations(engine)
        await test_pg_reservation_committed_after_count_before_reconcile(engine)
        await test_pg_check1_concurrency_regression(engine)
        logger.info("\n=======================================================")
        logger.info("ALL LIVE POSTGRESQL 16 CONCURRENCY TESTS PASSED 100%!")
        logger.info("=======================================================\n")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
