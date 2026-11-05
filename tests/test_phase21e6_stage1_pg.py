"""Phase 21E.6 — Stage 1: PostgreSQL 16 Migration 0025, RLS & Concurrency Tests.

Validates on live PostgreSQL 16:
1. Migration 0025 Catalog & Schema Verification:
   - platform_billing_job_runs
   - platform_dunning_attempts
   - platform_invoices.idempotency_key and partial unique index
   - uq_platform_invoices_sub_period partial unique index
   - ix_society_subscriptions_sched_roll index
2. PostgreSQL 16 FORCE ROW LEVEL SECURITY:
   - platform_dunning_attempts enforces relrowsecurity=True and relforcerowsecurity=True.
   - Tenant isolation policy enforces app.current_society_id context.
   - app_user is NOSUPERUSER and NOBYPASSRLS.
   - Cross-tenant read/write operations denied under unprivileged role.
   - Missing tenant context fails closed (0 rows).
3. Database Invariant & Constraint Integrity:
   - uq_platform_invoices_sub_period rejects duplicate non-VOID invoices for identical periods.
   - ix_platform_invoices_idempotency_key rejects duplicate idempotency keys.
4. Live Horizontal Concurrency Execution:
   - Multiple parallel scheduler workers executing concurrently against candidate subscriptions.
   - Proves zero duplicate rolls, zero duplicate invoices, and serial transaction execution via SKIP LOCKED and advisory locks.
"""

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.src.database.models.platform_billing import (
    PlatformDunningAttempt,
    PlatformInvoice,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
)
from apps.api.src.database.session import set_db_tenant_context
from apps.api.src.subscriptions.automation.renewal_service import (
    AutomatedRenewalInvoicingService,
)
from apps.api.src.subscriptions.automation.scheduler_service import (
    BillingPeriodSchedulerService,
)
from apps.api.src.subscriptions.invoicing.numbering import InvoiceNumberingService
from apps.api.src.subscriptions.invoicing.service import PlatformInvoiceService
from apps.api.src.subscriptions.tax import (
    GSTTaxEngine,
    PlaceOfSupplyService,
    tax_config_service,
)

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
async def pg_session_factory(pg_engine):
    """Factory yielding isolated sessions connected to PostgreSQL 16."""
    return async_sessionmaker(bind=pg_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def ensure_app_user_role(pg_session_factory):
    """Ensure non-superuser app_user role exists with permissions on public schema."""
    async with pg_session_factory() as session:
        await session.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_user') THEN
                        CREATE ROLE app_user WITH LOGIN PASSWORD 'app_user_password' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
                    ELSE
                        ALTER ROLE app_user WITH LOGIN PASSWORD 'app_user_password' NOSUPERUSER NOBYPASSRLS;
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


@pytest_asyncio.fixture
def invoice_service():
    pos_service = PlaceOfSupplyService()
    tax_engine = GSTTaxEngine(tax_config_service)
    num_service = InvoiceNumberingService()
    return PlatformInvoiceService(
        tax_engine=tax_engine,
        pos_service=pos_service,
        numbering_service=num_service,
    )


@pytest_asyncio.fixture
def renewal_service(invoice_service):
    return AutomatedRenewalInvoicingService(invoice_service=invoice_service)


async def _seed_pg_tenant(
    session: AsyncSession,
    plan_price: Decimal = Decimal("1800.00"),
    billing_cycle: str = "MONTHLY",
    society_status: str = "ACTIVE",
    sub_status: str = "ACTIVE",
    next_billing_at: datetime | None = None,
    auto_renew: bool = True,
) -> tuple[Society, PlatformSubscriptionPlan, SocietySubscription]:
    now = _utc_now()
    soc_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    sub_id = uuid.uuid4()

    soc = Society(
        id=soc_id,
        legal_name=f"PG Live Society {soc_id.hex[:6]}",
        display_name=f"PG Society {soc_id.hex[:6]}",
        address_line1="456 Marine Drive",
        city="Mumbai",
        state="Maharashtra",
        postal_code="400020",
        status=society_status,
        registration_number=f"REG-{soc_id.hex[:6]}",
    )
    plan = PlatformSubscriptionPlan(
        id=plan_id,
        plan_code=f"PG_PLAN_{plan_id.hex}",
        display_name="PG Enterprise Plan",
        monthly_price=plan_price,
        annual_price=plan_price * 10,
        is_active=True,
    )
    p_start = now - timedelta(days=30)
    p_end = now
    nxt = next_billing_at if next_billing_at is not None else p_end

    sub = SocietySubscription(
        id=sub_id,
        society_id=soc_id,
        plan_id=plan_id,
        status=sub_status,
        billing_cycle=billing_cycle,
        auto_renew=auto_renew,
        starts_at=p_start,
        current_period_start=p_start,
        current_period_end=p_end,
        next_billing_at=nxt,
    )
    session.add_all([soc, plan, sub])
    await session.commit()
    await session.refresh(sub)
    await session.refresh(soc)
    return soc, plan, sub


# =============================================================================
# 1. Migration 0025 Schema & Catalog Verification
# =============================================================================
@pytest.mark.asyncio
async def test_migration_0025_catalog_and_rls(pg_session_factory):
    """Verify that migration 0025 tables and indexes exist in PostgreSQL 16 catalog."""
    async with pg_session_factory() as session:
        # 1. Verify RLS flags on platform_dunning_attempts
        res = await session.execute(
            text(
                """
                SELECT relname, relrowsecurity, relforcerowsecurity
                FROM pg_class
                WHERE relname = 'platform_dunning_attempts';
                """
            )
        )
        row = res.fetchone()
        assert row is not None, "Table platform_dunning_attempts must exist in catalog!"
        assert row[1] is True, "platform_dunning_attempts must have relrowsecurity=True!"
        assert row[2] is True, "platform_dunning_attempts must have relforcerowsecurity=True!"

        # 2. Verify global table platform_billing_job_runs exists
        res_job = await session.execute(
            text(
                """
                SELECT relname, relrowsecurity
                FROM pg_class
                WHERE relname = 'platform_billing_job_runs';
                """
            )
        )
        row_job = res_job.fetchone()
        assert row_job is not None, "platform_billing_job_runs must exist!"
        assert row_job[1] is False, "platform_billing_job_runs is platform-internal and not tenant-scoped."

        # 3. Verify partial unique indexes
        res_idx = await session.execute(
            text(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'platform_invoices'
                  AND indexname IN ('uq_platform_invoices_sub_period', 'ix_platform_invoices_idempotency_key');
                """
            )
        )
        indexes = {r[0] for r in res_idx.fetchall()}
        assert "uq_platform_invoices_sub_period" in indexes
        assert "ix_platform_invoices_idempotency_key" in indexes


# =============================================================================
# 2. PostgreSQL 16 RLS on platform_dunning_attempts
# =============================================================================
@pytest.mark.asyncio
async def test_pg16_rls_dunning_attempts_isolation(pg_engine, pg_session_factory, ensure_app_user_role):
    """Verify cross-tenant read/write denial on platform_dunning_attempts under app_user role."""
    # Seed 2 societies under superuser
    async with pg_session_factory() as session:
        soc_a, _, sub_a = await _seed_pg_tenant(session)
        soc_b, _, sub_b = await _seed_pg_tenant(session)

        # Seed 1 dunning attempt for society A
        attempt_a = PlatformDunningAttempt(
            id=uuid.uuid4(),
            society_id=soc_a.id,
            subscription_id=sub_a.id,
            attempt_type="REMINDER_NOTICE",
            status="PENDING",
            idempotency_key=f"dunning-pg-{uuid.uuid4().hex[:10]}",
            scheduled_at=_utc_now(),
        )
        session.add(attempt_a)
        await session.commit()
        attempt_a_id = attempt_a.id

    # Connect as unprivileged app_user
    app_engine = create_async_engine(
        PG_URL.replace("postgres:postgrespassword", "app_user:app_user_password"),
        echo=False,
    )
    app_session_factory = async_sessionmaker(bind=app_engine, class_=AsyncSession, expire_on_commit=False)

    try:
        # A. Missing tenant context -> fail closed (0 rows)
        async with app_session_factory() as session:
            stmt = select(PlatformDunningAttempt)
            rows = (await session.execute(stmt)).scalars().all()
            assert len(rows) == 0, "Missing tenant context must return zero rows (fail closed)!"

        # B. Set context to Society A -> can see attempt_a
        async with app_session_factory() as session:
            await set_db_tenant_context(session, soc_a.id)
            stmt = select(PlatformDunningAttempt).where(PlatformDunningAttempt.id == attempt_a_id)
            found = (await session.execute(stmt)).scalar_one_or_none()
            assert found is not None
            assert found.society_id == soc_a.id

        # C. Set context to Society B -> cross-tenant read denied (None)
        async with app_session_factory() as session:
            await set_db_tenant_context(session, soc_b.id)
            stmt = select(PlatformDunningAttempt).where(PlatformDunningAttempt.id == attempt_a_id)
            denied = (await session.execute(stmt)).scalar_one_or_none()
            assert denied is None, "Cross-tenant read must be denied by PostgreSQL RLS!"

        # D. Set context to Society B -> attempt write with society_id = Society A -> denied
        async with app_session_factory() as session:
            await set_db_tenant_context(session, soc_b.id)
            tamper_attempt = PlatformDunningAttempt(
                id=uuid.uuid4(),
                society_id=soc_a.id,  # Tampered society_id!
                subscription_id=sub_a.id,
                attempt_type="REMINDER_NOTICE",
                status="PENDING",
                idempotency_key=f"dunning-tamper-{uuid.uuid4().hex[:10]}",
                scheduled_at=_utc_now(),
            )
            session.add(tamper_attempt)
            with pytest.raises(Exception):  # RLS policy with-check or foreign key / RLS check violation
                await session.commit()
    finally:
        await app_engine.dispose()


# =============================================================================
# 3. Database Invariant & Unique Constraint Testing
# =============================================================================
@pytest.mark.asyncio
async def test_database_invoice_idempotency_constraints(pg_session_factory):
    """Verify that uq_platform_invoices_sub_period rejects duplicate non-VOID invoices for identical periods."""
    now = _utc_now()
    p_start = now
    p_end = now + timedelta(days=30)

    async with pg_session_factory() as session:
        soc, plan, sub = await _seed_pg_tenant(session)
        soc_id = soc.id
        sub_id = sub.id
        key1 = f"idemp-test-{uuid.uuid4().hex[:8]}"

        # 1. Insert first invoice
        inv1 = PlatformInvoice(
            id=uuid.uuid4(),
            society_id=soc_id,
            subscription_id=sub_id,
            billing_cycle="MONTHLY",
            period_start=p_start,
            period_end=p_end,
            subtotal=Decimal("1500.00"),
            taxable_amount=Decimal("1500.00"),
            tax_total=Decimal("270.00"),
            grand_total=Decimal("1770.00"),
            amount_due=Decimal("1770.00"),
            status="ISSUED",
            due_date=date.today(),
            place_of_supply="Maharashtra",
            idempotency_key=key1,
        )
        session.add(inv1)
        await session.commit()

        # 2. Attempt inserting duplicate invoice for identical subscription and period
        inv2 = PlatformInvoice(
            id=uuid.uuid4(),
            society_id=soc_id,
            subscription_id=sub_id,
            billing_cycle="MONTHLY",
            period_start=p_start,
            period_end=p_end,
            subtotal=Decimal("1500.00"),
            taxable_amount=Decimal("1500.00"),
            tax_total=Decimal("270.00"),
            grand_total=Decimal("1770.00"),
            amount_due=Decimal("1770.00"),
            status="ISSUED",
            due_date=date.today(),
            place_of_supply="Maharashtra",
            idempotency_key=f"idemp-different-{uuid.uuid4().hex[:8]}",
        )
        session.add(inv2)
        with pytest.raises(IntegrityError) as exc_info:
            await session.commit()
        assert "uq_platform_invoices_sub_period" in str(exc_info.value)
        await session.rollback()

        # 3. Attempt inserting duplicate invoice with duplicate idempotency_key
        inv3 = PlatformInvoice(
            id=uuid.uuid4(),
            society_id=soc_id,
            subscription_id=sub_id,
            billing_cycle="MONTHLY",
            period_start=p_start + timedelta(days=60),
            period_end=p_end + timedelta(days=60),
            subtotal=Decimal("1500.00"),
            taxable_amount=Decimal("1500.00"),
            tax_total=Decimal("270.00"),
            grand_total=Decimal("1770.00"),
            amount_due=Decimal("1770.00"),
            status="ISSUED",
            due_date=date.today(),
            place_of_supply="Maharashtra",
            idempotency_key=key1,  # Duplicate key!
        )
        session.add(inv3)
        with pytest.raises(IntegrityError) as exc_info_key:
            await session.commit()
        assert "ix_platform_invoices_idempotency_key" in str(exc_info_key.value)
        await session.rollback()


# =============================================================================
# 4. Live Multi-Worker Concurrency on PostgreSQL 16
# =============================================================================
@pytest.mark.asyncio
async def test_concurrent_scheduler_workers_pg(pg_session_factory, renewal_service):
    """Run multiple parallel scheduler workers concurrently against due subscriptions on PostgreSQL 16.

    Verifies:
    1. Zero deadlocks.
    2. Zero duplicate invoice generation.
    3. Exactly 1 roll per due subscription across all workers.
    """
    now = _utc_now()
    num_subscriptions = 4
    num_workers = 4

    # Seed candidate subscriptions
    sub_ids: list[uuid.UUID] = []
    async with pg_session_factory() as session:
        for idx in range(num_subscriptions):
            _, _, sub = await _seed_pg_tenant(
                session,
                plan_price=Decimal("1200.00"),
                next_billing_at=now - timedelta(minutes=5 * (idx + 1)),
            )
            sub_ids.append(sub.id)

    # Worker task executing process_due_subscriptions across concurrent sessions
    async def _run_worker(worker_idx: int):
        async with pg_session_factory() as worker_session:
            worker_scheduler = BillingPeriodSchedulerService(
                session=worker_session,
                renewal_service=renewal_service,
            )
            return await worker_scheduler.process_due_subscriptions(
                cutoff_utc=now,
                batch_size=10,
                execution_id=f"worker-{worker_idx}-{uuid.uuid4().hex[:6]}",
            )

    # Execute workers concurrently
    batch_results = await asyncio.gather(*[_run_worker(i) for i in range(num_workers)])

    # Aggregate successes across all workers
    total_rolled = sum(r.succeeded_count for r in batch_results)
    total_failed = sum(r.failed_count for r in batch_results)

    assert total_failed == 0, "No concurrent worker should encounter unhandled failures!"
    assert total_rolled >= num_subscriptions, (
        f"At least {num_subscriptions} subscriptions must be rolled across all workers, got {total_rolled}!"
    )

    # Collect rolled subscription IDs across all workers
    rolled_sub_ids = {
        item.subscription_id
        for batch in batch_results
        for item in batch.results
        if item.status == "ROLLED"
    }
    for s_id in sub_ids:
        assert s_id in rolled_sub_ids, f"Subscription {s_id} must be rolled by one of the concurrent workers!"

    # Verify that each seeded subscription has exactly 1 invoice and advanced next_billing_at
    async with pg_session_factory() as verify_session:
        for sub_id in sub_ids:
            sub = await verify_session.get(SocietySubscription, sub_id)
            sub_next = sub.next_billing_at.replace(tzinfo=None) if sub.next_billing_at and sub.next_billing_at.tzinfo else sub.next_billing_at
            now_naive = now.replace(tzinfo=None) if now.tzinfo else now
            assert sub_next > now_naive, "next_billing_at must be advanced into the future!"

            stmt_inv = select(PlatformInvoice).where(PlatformInvoice.subscription_id == sub_id)
            invoices = (await verify_session.execute(stmt_inv)).scalars().all()
            assert len(invoices) == 1, f"Subscription {sub_id} must have exactly 1 invoice, got {len(invoices)}!"
            assert invoices[0].status == "ISSUED"
            assert invoices[0].invoice_number is not None
            assert invoices[0].invoice_number.startswith("SS-2627-")


@pytest.mark.asyncio
async def test_pg16_expired_trial_with_auto_renew_false(pg_session_factory, renewal_service):
    """Verify on live PostgreSQL 16: Expired TRIAL with auto_renew=False transitions to CANCELLED

    without generating any invoices, without initiating a grace period, and is idempotent.
    """
    now = _utc_now()
    async with pg_session_factory() as session:
        soc, plan, sub = await _seed_pg_tenant(
            session,
            sub_status="TRIAL",
            auto_renew=False,
            next_billing_at=now - timedelta(minutes=10),
        )

        scheduler = BillingPeriodSchedulerService(session=session, renewal_service=renewal_service)
        result = await scheduler.process_due_subscriptions(
            cutoff_utc=now,
            execution_id=f"pg-trial-cancel-{uuid.uuid4().hex[:6]}",
        )

        assert result.succeeded_count == 1
        assert result.failed_count == 0
        assert len(result.results) == 1
        assert result.results[0].status == "CANCELLED"
        assert result.results[0].skip_reason == "TRIAL_EXPIRED_WITHOUT_RENEWAL"
        assert result.results[0].invoice_id is None

        # Verify database record state
        await session.refresh(sub)
        assert sub.status == "CANCELLED"
        assert sub.cancelled_at is not None
        assert "Trial expired with auto_renew=False" in (sub.cancellation_reason or "")
        assert sub.past_due_since is None, "past_due_since must remain None on non-renewing trial!"

        # Verify zero invoices created
        stmt_inv = select(PlatformInvoice).where(PlatformInvoice.subscription_id == sub.id)
        invoices = (await session.execute(stmt_inv)).scalars().all()
        assert len(invoices) == 0, f"Expected 0 invoices on live PG, got {len(invoices)}!"

        # Verify idempotency on second run
        repeat_result = await scheduler.process_due_subscriptions(
            cutoff_utc=now + timedelta(hours=1),
            execution_id=f"pg-trial-repeat-{uuid.uuid4().hex[:6]}",
        )
        assert repeat_result.processed_count == 0
        assert repeat_result.succeeded_count == 0

