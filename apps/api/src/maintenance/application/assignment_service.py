"""Application Service for Work Order Assignments."""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.audit import AuditLog
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.maintenance import WorkOrderActivity, WorkOrderAssignment
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.repositories.membership_repository import MembershipRepository
from apps.api.src.maintenance.domain.enums import (
    WorkOrderActivityType,
    WorkOrderAssignmentType,
    WorkOrderStatus,
)
from apps.api.src.maintenance.domain.exceptions import (
    CrossSocietyWorkOrderError,
    WorkOrderNotFoundError,
)
from apps.api.src.maintenance.domain.state_machine import validate_status_transition
from apps.api.src.maintenance.infrastructure.repositories import (
    MaintenanceWorkOrderRepository,
    WorkOrderActivityRepository,
    WorkOrderAssignmentRepository,
)
from apps.api.src.maintenance.schemas import WorkOrderAssignmentCreateRequest


class WorkOrderAssignmentService:
    """Manages assignment and reassignment of work orders to users, teams, staff, or vendors."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.wo_repo = MaintenanceWorkOrderRepository(db)
        self.assignment_repo = WorkOrderAssignmentRepository(db)
        self.activity_repo = WorkOrderActivityRepository(db)
        self.auth_repo = AuthorizationRepository(db)
        self.membership_repo = MembershipRepository(db)

    async def assign_work_order(
        self,
        work_order_id: uuid.UUID,
        society_id: uuid.UUID,
        request: WorkOrderAssignmentCreateRequest,
        assigner: User,
    ) -> WorkOrderAssignment:
        wo = await self.wo_repo.get_by_id(work_order_id, society_id)
        if not wo:
            raise WorkOrderNotFoundError(str(work_order_id))

        # Validate target user belongs to same society if user assignment
        if request.assignment_type == WorkOrderAssignmentType.INTERNAL_USER and request.target_user_id:
            membership = await self.membership_repo.get_membership(request.target_user_id, society_id)
            if not membership:
                raise CrossSocietyWorkOrderError("Target assignee user does not belong to this society.")

        # Validate target staff profile is ACTIVE if staff assignment
        if request.assignment_type == WorkOrderAssignmentType.STAFF and request.target_user_id:
            from sqlalchemy import select

            from apps.api.src.database.models.staff import StaffProfile

            stmt = select(StaffProfile).where(
                StaffProfile.id == request.target_user_id,
                StaffProfile.society_id == society_id,
            )
            staff = (await self.db.execute(stmt)).scalar_one_or_none()
            if not staff or staff.status != "ACTIVE":
                raise CrossSocietyWorkOrderError(
                    "Target staff member is not active or does not belong to this society."
                )

        # Validate target vendor profile is ACTIVE if vendor assignment
        if request.assignment_type == WorkOrderAssignmentType.VENDOR and request.target_user_id:
            from sqlalchemy import select

            from apps.api.src.database.models.vendor import VendorAssignmentHistory, VendorProfile

            vendor_stmt = select(VendorProfile).where(
                VendorProfile.id == request.target_user_id,
                VendorProfile.society_id == society_id,
            )
            vendor = (await self.db.execute(vendor_stmt)).scalar_one_or_none()
            if not vendor or vendor.status != "ACTIVE":
                raise CrossSocietyWorkOrderError(
                    "Target vendor is not active or does not belong to this society."
                )

            vendor_hist = VendorAssignmentHistory(
                society_id=society_id,
                vendor_id=vendor.id,
                work_order_id=wo.id,
                event_type="ASSIGNED",
                notes=request.reason or "Assigned work order",
                actor_user_id=assigner.id,
            )
            self.db.add(vendor_hist)

        # Create Assignment record
        assignment = WorkOrderAssignment(
            society_id=society_id,
            work_order_id=wo.id,
            assignment_type=request.assignment_type.value,
            target_user_id=request.target_user_id,
            target_team_id=request.target_team_id,
            assigned_by_user_id=assigner.id,
            assigned_at=datetime.utcnow(),
            reason=request.reason,
        )
        assignment = await self.assignment_repo.create(assignment)

        # Update current assignment on Work Order
        wo.current_assignment_id = assignment.id

        # Update status to ASSIGNED if currently DRAFT or OPEN
        if wo.status in [WorkOrderStatus.DRAFT.value, WorkOrderStatus.OPEN.value]:
            validate_status_transition(wo.status, WorkOrderStatus.ASSIGNED.value)
            wo.status = WorkOrderStatus.ASSIGNED.value

        await self.wo_repo.update(wo)

        # Log timeline activity
        event_type = (
            WorkOrderActivityType.REASSIGNED.value
            if wo.current_assignment_id
            else WorkOrderActivityType.ASSIGNED.value
        )
        activity = WorkOrderActivity(
            society_id=society_id,
            work_order_id=wo.id,
            event_type=event_type,
            description=f"Assigned work order to target ({request.assignment_type.value}).",
            actor_user_id=assigner.id,
        )
        await self.activity_repo.create(activity)

        # Core Audit Log
        audit_entry = AuditLog(
            society_id=society_id,
            actor_user_id=assigner.id,
            action="WORK_ORDER_ASSIGNED",
            entity_type="MaintenanceWorkOrder",
            entity_id=str(wo.id),
            after_state={"assignment_id": str(assignment.id), "assignment_type": assignment.assignment_type},
        )
        self.db.add(audit_entry)

        return assignment
