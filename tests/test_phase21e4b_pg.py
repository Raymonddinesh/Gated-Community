"""Phase 21E.4B — Live PostgreSQL 16 Invoicing Concurrency, Pessimistic Locking & RLS Tests.

Validates against live PostgreSQL 16:
1. Concurrency and Pessimistic Row Locking on PlatformInvoiceSequence:
   - Parallel workers finalizing invoices concurrently serialize on SELECT ... FOR UPDATE.
   - Yields strictly unique, consecutive, gapless invoice numbers without race conditions or deadlocks.
2. Unique Constraint Enforcement:
   - Database constraint 'uq_platform_invoices_number' prohibits duplicate invoice numbers.
3. Transaction Rollback Atomicity:
   - Uncommitted finalization reverts sequence progression and preserves invoice state.
4. Tenant Isolation with PostgreSQL FORCE ROW LEVEL SECURITY:
   - Unprivileged app_user (NOSUPERUSER NOBYPASSRLS) cannot access another tenant's invoices,
     items, or immutable tax snapshots stored in PlatformSubscriptionAuditLog.
"""

import asyncio
import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.src.core.tenant_context import tenant_context
from apps.api.src.database.models.platform_billing import (
    PlatformInvoice,
    PlatformInvoiceItem,
    PlatformInvoiceSequence,
    PlatformSubscriptionAuditLog,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import (
    PlatformSubscriptionPlan,
    SocietySubscription,
)
from apps.api.src.database.session import set_db_tenant_context
from apps.api.src.subscriptions.invoicing.numbering import (
    InvoiceNumberingService,
    get_financial_year,
)
from apps.api.src.subscriptions.invoicing.schemas import (
    PlatformInvoiceCreateDraft,
    PlatformInvoiceItemCreate,
)
from apps.api.src.subscriptions.invoicing.service import PlatformInvoiceService
from apps.api.src.subscriptions.tax import (
    GSTTaxEngine,
    PlaceOfSupplyService,
    TaxSnapshot,
    TaxSnapshotService,
    tax_config_service,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_phase21e4b_pg")

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


async def _seed_test_society_and_subscription(session: AsyncSession, state: str = "Maharashtra"):
    soc_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    sub_id = uuid.uuid4()
    now = _utc_now()

    soc = Society(
        id=soc_id,
        legal_name=f"PG Invoicing Test Society {soc_id.hex[:6]}",
        display_name=f"PG Society {soc_id.hex[:6]}",
        address_line1="Test High Street",
        city="Mumbai",
        state=state,
        postal_code="400001",
    )
    plan = PlatformSubscriptionPlan(
        id=plan_id,
        plan_code=f"PG_TEST_{soc_id.hex[:6]}",
        display_name="PG Test Plan",
        monthly_price=Decimal("1500.00"),
    )
    sub = SocietySubscription(
        id=sub_id,
        society_id=soc_id,
        plan_id=plan_id,
        status="ACTIVE",
        starts_at=now,
        current_period_start=now,
        current_period_end=now,
    )
    session.add_all([soc, plan, sub])
    await session.commit()
    return soc_id, sub_id


@pytest.mark.asyncio
async def test_concurrent_invoice_numbering_sequential_locking(
    pg_session_factory, invoice_service
):
    """Multiple concurrent workers finalizing invoices concurrently serialize via SELECT ... FOR UPDATE.

    Verifies:
    1. Zero deadlocks or race condition collisions.
    2. Zero duplicate invoice numbers.
    3. Strictly consecutive sequence progression without numbers being skipped.
    """
    async with pg_session_factory() as session:
        soc_id, sub_id = await _seed_test_society_and_subscription(session)

    num_concurrent_workers = 8
    now = _utc_now()
    draft_invoice_ids: list[uuid.UUID] = []

    # 1. Create drafts
    for idx in range(num_concurrent_workers):
        async with pg_session_factory() as session:
            payload = PlatformInvoiceCreateDraft(
                society_id=soc_id,
                subscription_id=sub_id,
                billing_cycle="MONTHLY",
                period_start=now,
                period_end=now,
                due_date=date.today(),
                items=[
                    PlatformInvoiceItemCreate(
                        item_type="BASE_PLAN",
                        description=f"Concurrent Line Item {idx}",
                        unit_price=Decimal("2000.00"),
                    )
                ],
            )
            draft_res = await invoice_service.create_draft_invoice(session, payload)
            await session.commit()
            draft_invoice_ids.append(draft_res.id)

    # 2. Finalize all drafts concurrently across separate sessions/connections
    async def _worker_finalize(inv_id: uuid.UUID) -> str:
        async with pg_session_factory() as worker_session:
            async with worker_session.begin():
                res = await invoice_service.finalize_invoice(worker_session, inv_id)
                return res.invoice_number

    results = await asyncio.gather(*[_worker_finalize(inv_id) for inv_id in draft_invoice_ids])

    # 3. Assert strictly unique, valid, and consecutive numbers
    assert len(results) == num_concurrent_workers
    assert len(set(results)) == num_concurrent_workers, "All allocated invoice numbers must be strictly unique!"

    # Parse sequence numbers
    fy = get_financial_year(now)
    prefix = f"SS-{fy}-"
    seq_nums: list[int] = []
    for inv_num in results:
        assert inv_num.startswith(prefix)
        seq_part = int(inv_num[len(prefix):])
        seq_nums.append(seq_part)

    seq_nums.sort()
    # Check that sequence numbers form a strictly contiguous progression
    for i in range(len(seq_nums) - 1):
        assert seq_nums[i + 1] == seq_nums[i] + 1, f"Gap detected between {seq_nums[i]} and {seq_nums[i+1]}"

    # Verify that the sequence counter in the database matches the maximum sequence number
    async with pg_session_factory() as session:
        seq_row = await session.get(PlatformInvoiceSequence, fy)
        assert seq_row is not None
        assert seq_row.current_sequence >= max(seq_nums)


@pytest.mark.asyncio
async def test_database_unique_constraint_enforcement(pg_session_factory):
    """PostgreSQL enforces unique constraint uq_platform_invoices_number against duplicate invoice numbers."""
    soc_id = uuid.uuid4()
    sub_id = uuid.uuid4()
    now = _utc_now()
    duplicate_number = f"SS-DUP-{uuid.uuid4().hex[:6]}"

    async with pg_session_factory() as session:
        soc_id, sub_id = await _seed_test_society_and_subscription(session)

        # 1. Insert first invoice with number
        inv1 = PlatformInvoice(
            id=uuid.uuid4(),
            society_id=soc_id,
            subscription_id=sub_id,
            invoice_number=duplicate_number,
            status="ISSUED",
            due_date=date.today(),
            period_start=now,
            period_end=now,
            place_of_supply="Maharashtra",
            subtotal=Decimal("1000.00"),
            taxable_amount=Decimal("1000.00"),
            grand_total=Decimal("1180.00"),
            amount_due=Decimal("1180.00"),
        )
        session.add(inv1)
        await session.commit()

    # 2. Attempt to insert second invoice with identical invoice number
    async with pg_session_factory() as session:
        inv2 = PlatformInvoice(
            id=uuid.uuid4(),
            society_id=soc_id,
            subscription_id=sub_id,
            invoice_number=duplicate_number,
            status="ISSUED",
            due_date=date.today(),
            period_start=now,
            period_end=now,
            place_of_supply="Maharashtra",
            subtotal=Decimal("1000.00"),
            taxable_amount=Decimal("1000.00"),
            grand_total=Decimal("1180.00"),
            amount_due=Decimal("1180.00"),
        )
        session.add(inv2)
        with pytest.raises(IntegrityError) as exc_info:
            await session.commit()

        assert "uq_platform_invoices_number" in str(exc_info.value).lower() or "unique constraint" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_transaction_rollback_preservation(pg_session_factory, invoice_service):
    """An aborted/rolled-back finalization transaction preserves both invoice state and sequence counter."""
    async with pg_session_factory() as session:
        soc_id, sub_id = await _seed_test_society_and_subscription(session)
        now = _utc_now()
        payload = PlatformInvoiceCreateDraft(
            society_id=soc_id,
            subscription_id=sub_id,
            billing_cycle="MONTHLY",
            period_start=now,
            period_end=now,
            due_date=date.today(),
            items=[PlatformInvoiceItemCreate(description="Rollback test item", unit_price=Decimal("1000.00"))],
        )
        draft = await invoice_service.create_draft_invoice(session, payload)
        await session.commit()
        draft_id = draft.id

    fy = get_financial_year(now)
    # Get current sequence before attempt
    async with pg_session_factory() as session:
        seq_row = await session.get(PlatformInvoiceSequence, fy)
        initial_seq = seq_row.current_sequence if seq_row else 0

    # Simulate an error causing rollback during finalization transaction
    try:
        async with pg_session_factory() as session:
            async with session.begin():
                # Perform finalization within an explicit sub-context that will raise an error
                await invoice_service.finalize_invoice(session, draft_id)
                # Force an intentional error before commit
                raise RuntimeError("Intentional error simulating network/worker crash before commit")
    except RuntimeError:
        pass

    # Verify that the invoice row is STILL in DRAFT status and has no invoice number
    async with pg_session_factory() as session:
        inv_after = await session.get(PlatformInvoice, draft_id)
        assert inv_after.status == "DRAFT"
        assert inv_after.invoice_number is None

        # Verify sequence counter was NOT permanently incremented
        seq_after = await session.get(PlatformInvoiceSequence, fy)
        after_seq = seq_after.current_sequence if seq_after else 0
        assert after_seq == initial_seq, f"Sequence counter incremented despite rollback: {after_seq} != {initial_seq}"


@pytest.mark.asyncio
async def test_unprivileged_app_user_rls_isolation(
    pg_session_factory, invoice_service, ensure_app_user_role
):
    """Under unprivileged role 'app_user', PostgreSQL FORCE ROW LEVEL SECURITY isolates invoices and tax snapshots."""
    async with pg_session_factory() as session:
        soc_a_id, sub_a_id = await _seed_test_society_and_subscription(session, state="Maharashtra")
        soc_b_id, sub_b_id = await _seed_test_society_and_subscription(session, state="Karnataka")

        now = _utc_now()
        # Create and finalize invoice for Tenant A
        payload = PlatformInvoiceCreateDraft(
            society_id=soc_a_id,
            subscription_id=sub_a_id,
            billing_cycle="MONTHLY",
            period_start=now,
            period_end=now,
            due_date=date.today(),
            items=[
                PlatformInvoiceItemCreate(
                    description="Tenant A Growth Plan",
                    unit_price=Decimal("5000.00"),
                )
            ],
        )
        inv_a = await invoice_service.create_draft_invoice(session, payload)
        await session.commit()
        inv_a_id = inv_a.id

    async with pg_session_factory() as session:
        res_a = await invoice_service.finalize_invoice(session, inv_a_id)
        await session.commit()
        allocated_number = res_a.invoice_number

    # 1. Tenant B connects as unprivileged app_user -> cannot see Tenant A's invoice, items, or tax snapshots
    async with pg_session_factory() as session:
        await session.execute(text("SET ROLE app_user"))
        async with tenant_context(soc_b_id):
            await set_db_tenant_context(session, soc_b_id)

            # Query PlatformInvoice
            inv_leak = (
                await session.execute(
                    select(PlatformInvoice).where(PlatformInvoice.id == inv_a_id)
                )
            ).scalar_one_or_none()
            assert inv_leak is None, "FORCE RLS violation: Tenant B accessed Tenant A's invoice!"

            # Query PlatformInvoiceItem
            item_leak = (
                await session.execute(
                    select(PlatformInvoiceItem).where(PlatformInvoiceItem.invoice_id == inv_a_id)
                )
            ).scalars().all()
            assert len(item_leak) == 0, "FORCE RLS violation: Tenant B accessed Tenant A's invoice items!"

            # Query PlatformSubscriptionAuditLog (tax snapshot)
            snapshot_leak = (
                await session.execute(
                    select(PlatformSubscriptionAuditLog).where(
                        PlatformSubscriptionAuditLog.entity_id == inv_a_id,
                        PlatformSubscriptionAuditLog.entity_type == "INVOICE_TAX_SNAPSHOT",
                    )
                )
            ).scalar_one_or_none()
            assert snapshot_leak is None, "FORCE RLS violation: Tenant B accessed Tenant A's tax snapshot!"

    # 2. Tenant A connects as unprivileged app_user -> accesses own invoice, items, and tax snapshot
    async with pg_session_factory() as session:
        await session.execute(text("SET ROLE app_user"))
        async with tenant_context(soc_a_id):
            await set_db_tenant_context(session, soc_a_id)

            inv_a_read = (
                await session.execute(
                    select(PlatformInvoice).where(PlatformInvoice.id == inv_a_id)
                )
            ).scalar_one_or_none()
            assert inv_a_read is not None, "Tenant A must access their own invoice"
            assert inv_a_read.invoice_number == allocated_number
            assert inv_a_read.status == "ISSUED"

            items_a_read = (
                await session.execute(
                    select(PlatformInvoiceItem).where(PlatformInvoiceItem.invoice_id == inv_a_id)
                )
            ).scalars().all()
            assert len(items_a_read) == 1
            assert items_a_read[0].unit_price == Decimal("5000.00")

            snapshot_row = (
                await session.execute(
                    select(PlatformSubscriptionAuditLog).where(
                        PlatformSubscriptionAuditLog.entity_id == inv_a_id,
                        PlatformSubscriptionAuditLog.entity_type == "INVOICE_TAX_SNAPSHOT",
                    )
                )
            ).scalar_one_or_none()
            assert snapshot_row is not None, "Tenant A must access their own tax snapshot"
            assert snapshot_row.after_state is not None

            # Verify cryptographic SHA-256 digest of retrieved tax snapshot
            restored = TaxSnapshot(**snapshot_row.after_state)
            assert TaxSnapshotService.verify_snapshot_integrity(restored) is True
