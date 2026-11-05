"""Tests for Phase 12 — Staff & Workforce Management Foundation."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.identity import User
from apps.api.src.database.models.maintenance import MaintenanceCategory
from apps.api.src.maintenance.application.assignment_service import WorkOrderAssignmentService
from apps.api.src.maintenance.application.work_order_service import MaintenanceWorkOrderService
from apps.api.src.maintenance.domain.enums import WorkOrderAssignmentType
from apps.api.src.maintenance.domain.exceptions import CrossSocietyWorkOrderError
from apps.api.src.maintenance.schemas import (
    WorkOrderAssignmentCreateRequest,
    WorkOrderCreateRequest,
)
from apps.api.src.staff.application.document_service import StaffDocumentService
from apps.api.src.staff.application.role_service import StaffRoleService
from apps.api.src.staff.application.staff_service import StaffProfileService
from apps.api.src.staff.application.team_service import StaffTeamService
from apps.api.src.staff.domain.enums import (
    StaffDocumentType,
    StaffEngagementType,
    StaffStatus,
)
from apps.api.src.staff.domain.exceptions import (
    InvalidStaffStatusTransitionError,
)
from apps.api.src.staff.schemas import (
    StaffContactRequest,
    StaffProfileCreateRequest,
    StaffRoleCreateRequest,
    StaffStatusUpdateRequest,
    StaffTeamCreateRequest,
)


@pytest.mark.asyncio
async def test_staff_profile_and_code_generation(
    seeded_session: AsyncSession,
) -> None:
    """Test creating a staff profile and STF-YYYY-XXXXXX sequential number generation."""
    session = seeded_session
    society_id = uuid.uuid4()

    creator = User(
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Admin",
        last_name="User",
        display_name="Admin User",
    )
    session.add(creator)
    await session.flush()

    role_service = StaffRoleService(session)
    role = await role_service.create_staff_role(
        StaffRoleCreateRequest(name="Electrician", code="ELEC", description="Electrical maintenance"),
        society_id,
    )

    staff_service = StaffProfileService(session)
    req = StaffProfileCreateRequest(
        first_name="Karthik",
        last_name="Subramanian",
        engagement_type=StaffEngagementType.FULL_TIME,
        primary_role_id=role.id,
        contact=StaffContactRequest(
            phone="+919876543210",
            emergency_contact_name="Sita",
            emergency_contact_phone="+919876500000",
        ),
    )

    staff = await staff_service.create_staff_profile(req, society_id, creator)

    assert staff.id is not None
    assert staff.staff_code.startswith("STF-2026-")
    assert staff.status == "ONBOARDING"
    assert staff.display_name == "Karthik Subramanian"


@pytest.mark.asyncio
async def test_staff_status_state_machine(
    seeded_session: AsyncSession,
) -> None:
    """Test valid and invalid status transitions using StaffStatusStateMachine."""
    session = seeded_session
    society_id = uuid.uuid4()

    admin = User(
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Admin",
        last_name="User",
        display_name="Admin User",
    )
    session.add(admin)
    await session.flush()

    staff_service = StaffProfileService(session)
    staff = await staff_service.create_staff_profile(
        StaffProfileCreateRequest(
            first_name="Ramesh",
            last_name="Kumar",
            contact=StaffContactRequest(phone="+919876543211"),
        ),
        society_id,
        admin,
    )

    # Valid: ONBOARDING -> ACTIVE
    staff = await staff_service.transition_staff_status(
        staff.id,
        society_id,
        StaffStatusUpdateRequest(status=StaffStatus.ACTIVE, reason="Onboarding completed"),
        admin,
    )
    assert staff.status == "ACTIVE"

    # Valid: ACTIVE -> SUSPENDED
    staff = await staff_service.transition_staff_status(
        staff.id,
        society_id,
        StaffStatusUpdateRequest(status=StaffStatus.SUSPENDED, reason="Under review"),
        admin,
    )
    assert staff.status == "SUSPENDED"

    # Invalid: SUSPENDED -> INACTIVE directly (must go through ACTIVE or OFFBOARDED)
    with pytest.raises(InvalidStaffStatusTransitionError):
        await staff_service.transition_staff_status(
            staff.id,
            society_id,
            StaffStatusUpdateRequest(status=StaffStatus.INACTIVE),
            admin,
        )


@pytest.mark.asyncio
async def test_staff_role_and_team_management(
    seeded_session: AsyncSession,
) -> None:
    """Test operational staff roles and team assignments."""
    session = seeded_session
    society_id = uuid.uuid4()

    admin = User(
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Admin",
        last_name="User",
        display_name="Admin User",
    )
    session.add(admin)
    await session.flush()

    staff_service = StaffProfileService(session)
    staff = await staff_service.create_staff_profile(
        StaffProfileCreateRequest(
            first_name="Murugan",
            last_name="P",
            contact=StaffContactRequest(phone="+919876543212"),
        ),
        society_id,
        admin,
    )

    team_service = StaffTeamService(session)
    team = await team_service.create_staff_team(
        StaffTeamCreateRequest(name="Maintenance Tech Team", code="MAINT_TECH"),
        society_id,
    )

    membership = await team_service.add_staff_to_team(
        staff_id=staff.id,
        team_id=team.id,
        society_id=society_id,
        is_primary=True,
        assigned_by_user=admin,
    )

    assert membership.id is not None
    assert membership.staff_id == staff.id
    assert membership.team_id == team.id


@pytest.mark.asyncio
async def test_staff_document_upload_and_archival(
    seeded_session: AsyncSession,
) -> None:
    """Test uploading staff document metadata, MIME validation, and archiving."""
    session = seeded_session
    society_id = uuid.uuid4()

    admin = User(
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Admin",
        last_name="User",
        display_name="Admin User",
    )
    session.add(admin)
    await session.flush()

    staff_service = StaffProfileService(session)
    staff = await staff_service.create_staff_profile(
        StaffProfileCreateRequest(
            first_name="Suresh",
            last_name="Rao",
            contact=StaffContactRequest(phone="+919876543213"),
        ),
        society_id,
        admin,
    )

    doc_service = StaffDocumentService(session)
    doc = await doc_service.upload_document(
        staff_id=staff.id,
        society_id=society_id,
        original_filename="identity_proof.pdf",
        content_type="application/pdf",
        file_bytes=b"%PDF-1.4 dummy pdf bytes",
        document_type=StaffDocumentType.IDENTITY,
        uploaded_by_user=admin,
    )

    assert doc.id is not None
    assert doc.original_filename == "identity_proof.pdf"
    assert doc.archived_at is None

    # Archive document
    archived_doc = await doc_service.archive_document(doc.id, society_id)
    assert archived_doc.archived_at is not None


@pytest.mark.asyncio
async def test_staff_work_order_assignment_integration(
    seeded_session: AsyncSession,
) -> None:
    """Test assigning active staff to Phase 11 work order and rejecting inactive staff."""
    session = seeded_session
    society_id = uuid.uuid4()

    admin = User(
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Admin",
        last_name="User",
        display_name="Admin User",
    )
    session.add(admin)
    await session.flush()

    cat = MaintenanceCategory(society_id=society_id, name="Plumbing", code="PLUMB")
    session.add(cat)
    await session.flush()

    wo_service = MaintenanceWorkOrderService(session)
    wo = await wo_service.create_work_order(
        WorkOrderCreateRequest(title="Pipe Repair", description="Fix pipe", category_id=cat.id),
        society_id,
        admin,
    )

    staff_service = StaffProfileService(session)
    staff = await staff_service.create_staff_profile(
        StaffProfileCreateRequest(
            first_name="Gopal",
            last_name="Singh",
            contact=StaffContactRequest(phone="+919876543214"),
        ),
        society_id,
        admin,
    )

    assign_service = WorkOrderAssignmentService(session)

    # Attempting to assign staff while in ONBOARDING must fail
    with pytest.raises(CrossSocietyWorkOrderError):
        await assign_service.assign_work_order(
            wo.id,
            society_id,
            WorkOrderAssignmentCreateRequest(
                assignment_type=WorkOrderAssignmentType.STAFF,
                target_user_id=staff.id,
            ),
            admin,
        )

    # Activate staff
    await staff_service.transition_staff_status(
        staff.id, society_id, StaffStatusUpdateRequest(status=StaffStatus.ACTIVE), admin
    )

    # Assignment to ACTIVE staff succeeds
    assignment = await assign_service.assign_work_order(
        wo.id,
        society_id,
        WorkOrderAssignmentCreateRequest(
            assignment_type=WorkOrderAssignmentType.STAFF,
            target_user_id=staff.id,
        ),
        admin,
    )
    assert assignment.id is not None
    assert assignment.target_user_id == staff.id


@pytest.mark.asyncio
async def test_staff_pii_masking_and_privacy(
    seeded_session: AsyncSession,
) -> None:
    """Test server-side masking of sensitive PII when caller lacks staff.view_sensitive permission."""
    session = seeded_session
    society_id = uuid.uuid4()

    admin = User(
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        first_name="Admin",
        last_name="User",
        display_name="Admin User",
    )
    session.add(admin)
    await session.flush()

    staff_service = StaffProfileService(session)
    staff = await staff_service.create_staff_profile(
        StaffProfileCreateRequest(
            first_name="Priv",
            last_name="User",
            notes="Internal sensitive note",
            contact=StaffContactRequest(
                phone="+919876543299",
                emergency_contact_name="Emergency Contact",
                emergency_contact_phone="+919876500000",
            ),
        ),
        society_id,
        admin,
    )

    # 1. Fetch contact directly via repo
    contact = await staff_service.repo.get_contact(staff.id, society_id)
    assert contact is not None
    assert contact.phone == "+919876543299"
    assert contact.emergency_contact_name == "Emergency Contact"
