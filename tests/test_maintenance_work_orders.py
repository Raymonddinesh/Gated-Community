"""Tests for Phase 11 — Maintenance & Work Order Management Foundation."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.identity import User
from apps.api.src.database.models.maintenance import (
    MaintenanceCategory,
    MaintenanceSubcategory,
)
from apps.api.src.maintenance.application.assignment_service import WorkOrderAssignmentService
from apps.api.src.maintenance.application.comment_service import WorkOrderCommentService
from apps.api.src.maintenance.application.material_service import WorkOrderMaterialService
from apps.api.src.maintenance.application.resolution_service import WorkOrderResolutionService
from apps.api.src.maintenance.application.work_order_service import MaintenanceWorkOrderService
from apps.api.src.maintenance.domain.enums import (
    WorkOrderAssignmentType,
    WorkOrderCommentType,
    WorkOrderPriority,
    WorkOrderSource,
    WorkOrderStatus,
)
from apps.api.src.maintenance.domain.exceptions import (
    InvalidWorkOrderTransitionError,
)
from apps.api.src.maintenance.schemas import (
    WorkOrderAssignmentCreateRequest,
    WorkOrderCommentCreateRequest,
    WorkOrderCreateRequest,
    WorkOrderMaterialUsageCreateRequest,
    WorkOrderResolutionCreateRequest,
    WorkOrderResolutionVerifyRequest,
    WorkOrderStatusUpdateRequest,
)


@pytest.mark.asyncio
async def test_maintenance_category_and_subcategory_creation(
    seeded_session: AsyncSession,
) -> None:
    """Test creating categories and subcategories with society scoping."""
    session = seeded_session
    society_id = uuid.uuid4()

    cat = MaintenanceCategory(
        society_id=society_id,
        name="Plumbing Systems",
        code="PLUMB",
        description="Plumbing and water pipe issues",
    )
    session.add(cat)
    await session.flush()

    subcat = MaintenanceSubcategory(
        society_id=society_id,
        category_id=cat.id,
        name="Tap Leakage",
        code="TAP_LEAK",
    )
    session.add(subcat)
    await session.flush()

    assert cat.id is not None
    assert subcat.id is not None
    assert subcat.category_id == cat.id


@pytest.mark.asyncio
async def test_work_order_creation_and_number_generation(
    seeded_session: AsyncSession,
) -> None:
    """Test work order creation and WO-YYYY-XXXXXX number sequence generation."""
    session = seeded_session
    society_id = uuid.uuid4()

    user = User(
        email=f"requester-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="John",
        last_name="Doe",
        display_name="John Doe",
    )
    session.add(user)
    await session.flush()

    cat = MaintenanceCategory(
        society_id=society_id,
        name="Electrical",
        code="ELEC",
    )
    session.add(cat)
    await session.flush()

    service = MaintenanceWorkOrderService(session)
    req = WorkOrderCreateRequest(
        title="Main Switchboard Sparking",
        description="Frequent sparking observed near main switchboard.",
        category_id=cat.id,
        priority=WorkOrderPriority.HIGH,
        source=WorkOrderSource.EMERGENCY,
    )

    wo = await service.create_work_order(req, society_id, user)

    assert wo.id is not None
    assert wo.work_order_number.startswith("WO-2026-")
    assert wo.priority == "HIGH"
    assert wo.status == "OPEN"


@pytest.mark.asyncio
async def test_work_order_state_machine_transitions(
    seeded_session: AsyncSession,
) -> None:
    """Test valid and invalid work order status state machine transitions."""
    session = seeded_session
    society_id = uuid.uuid4()

    user = User(
        email=f"tech-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Tech",
        last_name="Lead",
        display_name="Tech Lead",
    )
    session.add(user)
    await session.flush()

    cat = MaintenanceCategory(society_id=society_id, name="Civil", code="CIVIL")
    session.add(cat)
    await session.flush()

    service = MaintenanceWorkOrderService(session)
    wo = await service.create_work_order(
        WorkOrderCreateRequest(
            title="Wall Crack Inspection",
            description="Inspect boundary wall crack.",
            category_id=cat.id,
        ),
        society_id,
        user,
    )

    # Valid: OPEN -> IN_PROGRESS
    wo_updated = await service.transition_status(
        wo.id, society_id, WorkOrderStatusUpdateRequest(status=WorkOrderStatus.IN_PROGRESS), user
    )
    assert wo_updated.status == "IN_PROGRESS"

    # Invalid: IN_PROGRESS -> CLOSED directly without resolution
    with pytest.raises(InvalidWorkOrderTransitionError):
        await service.transition_status(
            wo.id, society_id, WorkOrderStatusUpdateRequest(status=WorkOrderStatus.CLOSED), user
        )


@pytest.mark.asyncio
async def test_work_order_assignment_lifecycle(
    seeded_session: AsyncSession,
) -> None:
    """Test assigning a work order to a target user and preserving history."""
    session = seeded_session
    society_id = uuid.uuid4()

    assigner = User(
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Admin",
        last_name="User",
        display_name="Admin User",
    )
    target = User(
        email=f"target-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Target",
        last_name="Worker",
        display_name="Target Worker",
    )
    session.add_all([assigner, target])
    await session.flush()

    from apps.api.src.database.models.membership import UserSocietyMembership

    membership = UserSocietyMembership(
        user_id=target.id,
        society_id=society_id,
        membership_status="ACTIVE",
    )
    session.add(membership)
    await session.flush()

    cat = MaintenanceCategory(society_id=society_id, name="Cleaning", code="CLEAN")
    session.add(cat)
    await session.flush()

    wo_service = MaintenanceWorkOrderService(session)
    wo = await wo_service.create_work_order(
        WorkOrderCreateRequest(
            title="Stairwell Cleaning", description="Clean stairwell B", category_id=cat.id
        ),
        society_id,
        assigner,
    )

    assign_service = WorkOrderAssignmentService(session)
    assignment = await assign_service.assign_work_order(
        wo.id,
        society_id,
        WorkOrderAssignmentCreateRequest(
            assignment_type=WorkOrderAssignmentType.INTERNAL_USER,
            target_user_id=target.id,
            reason="Assigned to primary janitorial lead",
        ),
        assigner,
    )

    assert assignment.id is not None
    assert assignment.target_user_id == target.id

    # Reload WO
    reloaded_wo = await wo_service.get_work_order(wo.id, society_id, assigner, has_view_all=True)
    assert reloaded_wo.status == "ASSIGNED"


@pytest.mark.asyncio
async def test_work_order_comments_privacy(
    seeded_session: AsyncSession,
) -> None:
    """Test public vs internal comment creation and resident filtering."""
    session = seeded_session
    society_id = uuid.uuid4()

    staff = User(
        email=f"staff-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Staff",
        last_name="Member",
        display_name="Staff Member",
    )
    resident = User(
        email=f"resident-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Res",
        last_name="User",
        display_name="Res User",
    )
    session.add_all([staff, resident])
    await session.flush()

    cat = MaintenanceCategory(society_id=society_id, name="General", code="GEN")
    session.add(cat)
    await session.flush()

    wo_service = MaintenanceWorkOrderService(session)
    wo = await wo_service.create_work_order(
        WorkOrderCreateRequest(
            title="Gate Hinge Noise", description="Gate hinge squeaking", category_id=cat.id
        ),
        society_id,
        resident,
    )

    comment_service = WorkOrderCommentService(session)

    # Public comment by resident
    await comment_service.add_comment(
        wo.id,
        society_id,
        WorkOrderCommentCreateRequest(comment_text="Please fix before 6pm"),
        resident,
        has_internal_perm=False,
    )

    # Internal note by staff
    await comment_service.add_comment(
        wo.id,
        society_id,
        WorkOrderCommentCreateRequest(
            comment_text="Vendor quote pending: Rs 500", comment_type=WorkOrderCommentType.INTERNAL
        ),
        staff,
        has_internal_perm=True,
    )

    # Resident view should omit internal notes
    res_comments = await comment_service.list_comments(wo.id, society_id, resident, has_internal_perm=False)
    assert len(res_comments) == 1
    assert res_comments[0].comment_text == "Please fix before 6pm"

    # Staff view should include both
    staff_comments = await comment_service.list_comments(wo.id, society_id, staff, has_internal_perm=True)
    assert len(staff_comments) == 2


@pytest.mark.asyncio
async def test_work_order_material_usage_operational_tracker(
    seeded_session: AsyncSession,
) -> None:
    """Test operational material usage logging with Decimal precision."""
    session = seeded_session
    society_id = uuid.uuid4()

    user = User(
        email=f"tech-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Tech",
        last_name="Worker",
        display_name="Tech Worker",
    )
    session.add(user)
    await session.flush()

    cat = MaintenanceCategory(society_id=society_id, name="Plumbing", code="PLUMB")
    session.add(cat)
    await session.flush()

    wo_service = MaintenanceWorkOrderService(session)
    wo = await wo_service.create_work_order(
        WorkOrderCreateRequest(
            title="Pipe Replacement", description="Replace corroded PVC pipe", category_id=cat.id
        ),
        society_id,
        user,
    )

    mat_service = WorkOrderMaterialService(session)
    mat = await mat_service.add_material_usage(
        wo.id,
        society_id,
        WorkOrderMaterialUsageCreateRequest(
            material_name="2-inch PVC Pipe",
            quantity=Decimal("3.50"),
            unit="meters",
            estimated_unit_cost=Decimal("150.00"),
            actual_unit_cost=Decimal("145.50"),
        ),
        user,
    )

    assert mat.id is not None
    assert mat.quantity == Decimal("3.50")
    assert mat.actual_unit_cost == Decimal("145.50")


@pytest.mark.asyncio
async def test_work_order_resolution_and_verification_flow(
    seeded_session: AsyncSession,
) -> None:
    """Test completing, verifying, and closing a work order."""
    session = seeded_session
    society_id = uuid.uuid4()

    tech = User(
        email=f"tech-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Tech",
        last_name="Person",
        display_name="Tech Person",
    )
    verifier = User(
        email=f"manager-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Facility",
        last_name="Manager",
        display_name="Facility Manager",
    )
    session.add_all([tech, verifier])
    await session.flush()

    cat = MaintenanceCategory(society_id=society_id, name="Electrical", code="ELEC")
    session.add(cat)
    await session.flush()

    wo_service = MaintenanceWorkOrderService(session)
    wo = await wo_service.create_work_order(
        WorkOrderCreateRequest(
            title="Light Fixture Replacement", description="Replace 4 LED lamps", category_id=cat.id
        ),
        society_id,
        tech,
    )
    await wo_service.transition_status(
        wo.id, society_id, WorkOrderStatusUpdateRequest(status=WorkOrderStatus.IN_PROGRESS), tech
    )

    res_service = WorkOrderResolutionService(session)
    resolution = await res_service.complete_work_order(
        wo.id,
        society_id,
        WorkOrderResolutionCreateRequest(resolution_summary="Replaced 4 LED tubelights in hallway"),
        tech,
    )
    assert resolution.status == "PENDING_VERIFICATION"

    # Verify resolution
    res_verified = await res_service.verify_resolution(
        wo.id,
        society_id,
        WorkOrderResolutionVerifyRequest(
            accepted=True, verification_comment="Inspected and confirmed operational"
        ),
        verifier,
    )
    assert res_verified.status == "VERIFIED"

    # Close work order
    wo_closed = await res_service.close_work_order(wo.id, society_id, verifier)
    assert wo_closed.status == "CLOSED"
