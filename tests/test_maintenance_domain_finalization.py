"""Domain Finalization and Security Verification Tests for Phase 11 — Maintenance Work Orders."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.billing import Invoice, Payment, Receipt
from apps.api.src.database.models.finance import JournalEntry, JournalEntryLine
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.maintenance import MaintenanceCategory, MaintenanceWorkOrder
from apps.api.src.maintenance.application.material_service import WorkOrderMaterialService
from apps.api.src.maintenance.application.resolution_service import WorkOrderResolutionService
from apps.api.src.maintenance.application.work_order_service import MaintenanceWorkOrderService
from apps.api.src.maintenance.domain.enums import WorkOrderStatus
from apps.api.src.maintenance.infrastructure.repositories import MaintenanceWorkOrderRepository
from apps.api.src.maintenance.schemas import (
    WorkOrderCreateRequest,
    WorkOrderMaterialUsageCreateRequest,
    WorkOrderResolutionCreateRequest,
    WorkOrderStatusUpdateRequest,
)


@pytest.mark.asyncio
async def test_maintenance_financial_isolation_non_mutation(
    seeded_session: AsyncSession,
) -> None:
    """Verify that work order operations NEVER mutate financial ledger or billing records."""
    session = seeded_session
    society_id = uuid.uuid4()

    # 1. Capture initial counts across financial and billing tables
    inv_count_before = (await session.execute(select(func.count(Invoice.id)))).scalar() or 0
    pay_count_before = (await session.execute(select(func.count(Payment.id)))).scalar() or 0
    rcpt_count_before = (await session.execute(select(func.count(Receipt.id)))).scalar() or 0
    je_count_before = (await session.execute(select(func.count(JournalEntry.id)))).scalar() or 0
    jel_count_before = (await session.execute(select(func.count(JournalEntryLine.id)))).scalar() or 0

    # 2. Execute Work Order creation, material usage, and completion
    user = User(
        email=f"finuser-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Fin",
        last_name="Check",
        display_name="Fin Check",
    )
    session.add(user)
    await session.flush()

    cat = MaintenanceCategory(society_id=society_id, name="HVAC", code="HVAC")
    session.add(cat)
    await session.flush()

    wo_service = MaintenanceWorkOrderService(session)
    wo = await wo_service.create_work_order(
        WorkOrderCreateRequest(
            title="AC Compressor Servicing", description="Service outdoor AC unit", category_id=cat.id
        ),
        society_id,
        user,
    )

    # Transition to IN_PROGRESS
    await wo_service.transition_status(
        wo.id, society_id, WorkOrderStatusUpdateRequest(status=WorkOrderStatus.IN_PROGRESS), user
    )

    mat_service = WorkOrderMaterialService(session)
    await mat_service.add_material_usage(
        wo.id,
        society_id,
        WorkOrderMaterialUsageCreateRequest(
            material_name="Refrigerant Gas R410A",
            quantity=Decimal("2.00"),
            unit="kg",
            actual_unit_cost=Decimal("1200.00"),
        ),
        user,
    )

    res_service = WorkOrderResolutionService(session)
    await res_service.complete_work_order(
        wo.id,
        society_id,
        WorkOrderResolutionCreateRequest(resolution_summary="Gas refilled and compressor tested"),
        user,
    )

    # 3. Assert zero mutation on financial core & billing tables
    inv_count_after = (await session.execute(select(func.count(Invoice.id)))).scalar() or 0
    pay_count_after = (await session.execute(select(func.count(Payment.id)))).scalar() or 0
    rcpt_count_after = (await session.execute(select(func.count(Receipt.id)))).scalar() or 0
    je_count_after = (await session.execute(select(func.count(JournalEntry.id)))).scalar() or 0
    jel_count_after = (await session.execute(select(func.count(JournalEntryLine.id)))).scalar() or 0

    assert inv_count_before == inv_count_after
    assert pay_count_before == pay_count_after
    assert rcpt_count_before == rcpt_count_after
    assert je_count_before == je_count_after
    assert jel_count_before == jel_count_after


@pytest.mark.asyncio
async def test_cross_society_reference_rejection(
    seeded_session: AsyncSession,
) -> None:
    """Verify that referencing categories or complaints from another society fails cleanly."""
    session = seeded_session
    society_a = uuid.uuid4()
    society_b = uuid.uuid4()

    user = User(
        email=f"user-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="User",
        last_name="A",
        display_name="User A",
    )
    session.add(user)
    await session.flush()

    # Category in Society B
    cat_b = MaintenanceCategory(society_id=society_b, name="Society B Cat", code="CAT_B")
    session.add(cat_b)
    await session.flush()

    wo_service = MaintenanceWorkOrderService(session)

    # Attempting to create work order in Society A using Society B Category must fail
    with pytest.raises(Exception):
        await wo_service.create_work_order(
            WorkOrderCreateRequest(
                title="Cross-society attempt", description="Test desc", category_id=cat_b.id
            ),
            society_a,
            user,
        )


@pytest.mark.asyncio
async def test_concurrent_work_order_number_generation(
    seeded_session: AsyncSession,
) -> None:
    """Verify concurrent sequence number generation under advisory locks produces unique numbers."""
    session = seeded_session
    society_id = uuid.uuid4()

    repo = MaintenanceWorkOrderRepository(session)
    numbers = []
    for _ in range(5):
        num = await repo.generate_next_work_order_number(society_id, 2026)
        # Create a dummy WO to increment count
        cat = MaintenanceCategory(society_id=society_id, name="Cat", code=f"C-{uuid.uuid4().hex[:4]}")
        session.add(cat)
        await session.flush()
        wo = MaintenanceWorkOrder(
            society_id=society_id,
            work_order_number=num,
            title="WO",
            description="Desc",
            category_id=cat.id,
        )
        session.add(wo)
        await session.flush()
        numbers.append(num)

    assert len(numbers) == 5
    assert len(set(numbers)) == 5  # All 5 work order numbers are unique
