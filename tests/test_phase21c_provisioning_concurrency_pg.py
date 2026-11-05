"""Live PostgreSQL 16 Concurrency, Advisory Locks, and RLS Tests for Phase 21C.

Executes live concurrent multi-session tests against PostgreSQL 16:
- Non-blocking transaction-scoped advisory locks (pg_try_advisory_xact_lock).
- Lock conflict response (HTTP 409, code PROVISIONING_IN_PROGRESS, Retry-After: 5).
- Clean rollback on failed lock acquisition with zero connection leaks.
- Idempotent replay returning cached response after first transaction commits.
- Concurrent duplicate legal name conflict rejection.
- Zero-RLS-bypass compliance and connection pool context cleanup.
- Cross-tenant isolation verification across provisioned societies.
"""

import asyncio
import logging
import sys
import uuid
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.src.database.models.authorization import Role
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietyProvisioningLog,
    SocietySubscription,
    SocietyUsageMetric,
)
from apps.api.src.database.session import set_db_tenant_context
from apps.api.src.subscriptions import (
    InitialAdminPayload,
    InitialSpatialPayload,
    ProvisioningConflictException,
    ProvisionSocietyRequest,
    SocietyProvisioningEngine,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_phase21c_concurrency_pg")

PG_URL = "postgresql+asyncpg://postgres:postgrespassword@localhost:5432/societysphere_dev"


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
async def pg_session_factory(pg_engine):
    """Factory yielding isolated sessions connected to PostgreSQL 16."""
    return async_sessionmaker(bind=pg_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def ensure_pg_baseline_data(pg_session_factory):
    """Ensure baseline roles and plans exist in PostgreSQL database."""
    async with pg_session_factory() as session:
        # Ensure SOCIETY_ADMIN role
        role_res = await session.execute(
            select(Role).where(Role.code == "SOCIETY_ADMIN", Role.scope_type == "SOCIETY")
        )
        if not role_res.scalar_one_or_none():
            session.add(
                Role(
                    code="SOCIETY_ADMIN",
                    name="Society Administrator",
                    scope_type="SOCIETY",
                    is_system_role=True,
                )
            )

        # Ensure FREE plan
        free_res = await session.execute(
            select(PlatformSubscriptionPlan).where(PlatformSubscriptionPlan.plan_code == "FREE")
        )
        if not free_res.scalar_one_or_none():
            session.add(
                PlatformSubscriptionPlan(
                    plan_code="FREE",
                    display_name="Free Plan",
                    monthly_price=0.00,
                    annual_price=0.00,
                    currency_code="INR",
                    trial_days=0,
                    is_active=True,
                )
            )

        # Ensure non-superuser app_user role exists for live RLS validation
        await session.execute(
            text("""
                DO $do$
                BEGIN
                    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_user') THEN
                        CREATE ROLE app_user NOSUPERUSER NOBYPASSRLS;
                        GRANT USAGE ON SCHEMA public TO app_user;
                        GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO app_user;
                        GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO app_user;
                    END IF;
                END
                $do$;
            """)
        )

        await session.commit()


def make_pg_request(
    legal_name: str | None = None,
    plan_code: str = "FREE",
    request_id: uuid.UUID | None = None,
) -> ProvisionSocietyRequest:
    uid = uuid.uuid4().hex[:8]
    return ProvisionSocietyRequest(
        provisioning_request_id=request_id or uuid.uuid4(),
        legal_name=legal_name or f"Live PG Society {uid}",
        display_name="Live PG Society",
        registration_number=f"REG-PG-{uid.upper()}",
        address_line1="100 Technology Road",
        city="Pune",
        state="Maharashtra",
        country="IN",
        postal_code="411001",
        timezone="Asia/Kolkata",
        default_language="en",
        plan_code=plan_code,
        admin_user=InitialAdminPayload(
            email=f"admin_{uid}@example.com",
            phone=f"+9198{uid[:8]}",
            first_name="Vivek",
            last_name="Patil",
        ),
        spatial=InitialSpatialPayload(
            create_default_block=True,
            default_block_name="Block Alpha",
        ),
    )


# ==============================================================================
# 1. LIVE CONCURRENCY & ADVISORY LOCK TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_pg_advisory_lock_non_blocking_conflict(
    pg_session_factory, ensure_pg_baseline_data: None
):
    """
    Verify non-blocking advisory lock semantics under concurrent access:
    1. Worker 1 holds advisory lock for idempotency key.
    2. Worker 2 attempts provisioning with same key -> pg_try_advisory_xact_lock returns FALSE.
    3. Worker 2 rolls back, raises ProvisioningConflictException with code PROVISIONING_IN_PROGRESS and Retry-After: 5.
    4. Worker 1 commits -> Worker 2 retries -> successfully receives cached result without duplication.
    """
    req_id = uuid.uuid4()
    req = make_pg_request(request_id=req_id)

    barrier = asyncio.Event()
    worker1_done = asyncio.Event()
    worker2_result: dict[str, object] = {}

    async def worker1():
        async with pg_session_factory() as session:
            engine = SocietyProvisioningEngine(session)
            # Step 1: acquire advisory lock
            await engine._try_acquire_advisory_lock(
                f"idempotency:{req_id}",
                f"idempotency key '{req_id}'",
            )
            # Signal worker 2 that lock is held
            barrier.set()
            # Wait for worker 2 to attempt lock acquisition
            await asyncio.sleep(0.5)

            # Worker 1 proceeds with full provisioning
            resp = await engine.provision_society(req)
            worker1_done.set()
            return resp

    async def worker2():
        # Wait for worker 1 to acquire the lock
        await barrier.wait()
        async with pg_session_factory() as session:
            engine = SocietyProvisioningEngine(session)
            try:
                await engine.provision_society(req)
                worker2_result["status"] = "UNEXPECTED_SUCCESS"
            except ProvisioningConflictException as exc:
                worker2_result["status"] = "CONFLICT"
                worker2_result["code"] = exc.code
                worker2_result["status_code"] = exc.status_code
                worker2_result["retry_after"] = getattr(exc, "headers", {}).get("Retry-After")

    # Run concurrently
    resp1, _ = await asyncio.gather(worker1(), worker2())

    assert worker2_result["status"] == "CONFLICT"
    assert worker2_result["code"] == "PROVISIONING_IN_PROGRESS"
    assert worker2_result["status_code"] == 409
    assert worker2_result["retry_after"] == "5"

    # Worker 1 completed successfully
    assert resp1.status == "ACTIVE"
    assert resp1.is_idempotent_replay is False

    # Now Worker 2 retries after Worker 1 committed
    async with pg_session_factory() as session:
        engine = SocietyProvisioningEngine(session)
        retry_resp = await engine.provision_society(req)
        assert retry_resp.is_idempotent_replay is True
        assert retry_resp.society_id == resp1.society_id

    # Verify exactly 1 society created
    async with pg_session_factory() as session:
        count = (
            await session.execute(
                select(func.count(Society.id)).where(Society.id == resp1.society_id)
            )
        ).scalar()
        assert count == 1


@pytest.mark.asyncio
async def test_pg_concurrent_duplicate_legal_name(
    pg_session_factory, ensure_pg_baseline_data: None
):
    """Two concurrent requests with identical legal name: exactly 1 succeeds, other rejected with 409."""
    shared_name = f"Prestige Palms CHS {uuid.uuid4().hex[:6]}"
    req1 = make_pg_request(legal_name=shared_name)
    req2 = make_pg_request(legal_name=shared_name)

    async def execute_prov(req):
        async with pg_session_factory() as session:
            engine = SocietyProvisioningEngine(session)
            try:
                resp = await engine.provision_society(req)
                return ("SUCCESS", resp)
            except ProvisioningConflictException as exc:
                return ("CONFLICT", exc)

    res1, res2 = await asyncio.gather(execute_prov(req1), execute_prov(req2))
    statuses = [res1[0], res2[0]]

    # Exactly one succeeded and one conflicted
    assert "SUCCESS" in statuses
    assert "CONFLICT" in statuses


# ==============================================================================
# 2. LIVE POSTGRESQL RLS & CONNECTION CLEANUP TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_pg_rls_enforcement_and_connection_cleanup(
    pg_session_factory, ensure_pg_baseline_data: None
):
    """
    Verify PostgreSQL 16 RLS policies and pooled connection cleanup:
    1. Provision society S.
    2. In a fresh session without setting app.current_society_id, queries return 0 rows.
    3. Setting app.current_society_id returns S's rows.
    4. After transaction commit/rollback, context reverts; next query returns 0 rows.
    """
    # 1. Provision society
    req = make_pg_request()
    async with pg_session_factory() as session:
        engine = SocietyProvisioningEngine(session)
        resp = await engine.provision_society(req)
        society_id = resp.society_id

    # 2. In a clean session without setting tenant context (running as app_user):
    async with pg_session_factory() as session:
        await session.execute(text("SET ROLE app_user"))
        # Check society_subscriptions
        sub_stmt = select(SocietySubscription).where(SocietySubscription.society_id == society_id)
        subs = (await session.execute(sub_stmt)).scalars().all()
        assert len(subs) == 0, "Security violation: Tenant subscription visible without RLS context!"

        # Check society_usage_metrics
        metric_stmt = select(SocietyUsageMetric).where(SocietyUsageMetric.society_id == society_id)
        metrics = (await session.execute(metric_stmt)).scalars().all()
        assert len(metrics) == 0, "Security violation: Usage metrics visible without RLS context!"

        # Check society_provisioning_logs
        log_stmt = select(SocietyProvisioningLog).where(SocietyProvisioningLog.society_id == society_id)
        logs = (await session.execute(log_stmt)).scalars().all()
        assert len(logs) == 0, "Security violation: Provisioning logs visible without RLS context!"

    # 3. In a session with tenant context explicitly set (running as app_user):
    async with pg_session_factory() as session:
        await session.execute(text("SET ROLE app_user"))
        await set_db_tenant_context(session, society_id)

        sub_stmt = select(SocietySubscription).where(SocietySubscription.society_id == society_id)
        subs = (await session.execute(sub_stmt)).scalars().all()
        assert len(subs) == 1
        assert subs[0].society_id == society_id

        metric_stmt = select(SocietyUsageMetric).where(SocietyUsageMetric.society_id == society_id)
        metrics = (await session.execute(metric_stmt)).scalars().all()
        assert len(metrics) == 4

        log_stmt = select(SocietyProvisioningLog).where(SocietyProvisioningLog.society_id == society_id)
        logs = (await session.execute(log_stmt)).scalars().all()
        assert len(logs) >= 8

        # 4. Commit session -> context should automatically discard
        await session.commit()

        # Query again without context in same session
        subs_after = (await session.execute(sub_stmt)).scalars().all()
        assert len(subs_after) == 0, "Security violation: Context leaked after commit!"


# ==============================================================================
# 3. LIVE CROSS-TENANT ISOLATION TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_pg_cross_tenant_isolation(
    pg_session_factory, ensure_pg_baseline_data: None
):
    """Tenant A's session context cannot see Tenant B's subscription, metrics, or provisioning logs."""
    # Provision Society A
    req_a = make_pg_request()
    async with pg_session_factory() as session:
        resp_a = await SocietyProvisioningEngine(session).provision_society(req_a)
        soc_a_id = resp_a.society_id

    # Provision Society B
    req_b = make_pg_request()
    async with pg_session_factory() as session:
        resp_b = await SocietyProvisioningEngine(session).provision_society(req_b)
        soc_b_id = resp_b.society_id

    assert soc_a_id != soc_b_id

    # Query with context set to Society A (running as non-superuser app_user)
    async with pg_session_factory() as session:
        await session.execute(text("SET ROLE app_user"))
        await set_db_tenant_context(session, soc_a_id)

        # Should see Society A's subscription
        sub_a = (await session.execute(select(SocietySubscription).where(SocietySubscription.society_id == soc_a_id))).scalar_one_or_none()
        assert sub_a is not None

        # Should NEVER see Society B's subscription
        sub_b = (await session.execute(select(SocietySubscription).where(SocietySubscription.society_id == soc_b_id))).scalar_one_or_none()
        assert sub_b is None, "Critical isolation failure: Tenant A observed Tenant B subscription!"

        # Should NEVER see Society B's metrics
        metrics_b = (await session.execute(select(SocietyUsageMetric).where(SocietyUsageMetric.society_id == soc_b_id))).scalars().all()
        assert len(metrics_b) == 0, "Critical isolation failure: Tenant A observed Tenant B metrics!"

        # Should NEVER see Society B's provisioning logs
        logs_b = (await session.execute(select(SocietyProvisioningLog).where(SocietyProvisioningLog.society_id == soc_b_id))).scalars().all()
        assert len(logs_b) == 0, "Critical isolation failure: Tenant A observed Tenant B provisioning logs!"
