"""Application Service for Work Order Resolution, Verification, and Linked Complaint Synchronization."""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.complaints.application.status_service import ComplaintStatusService
from apps.api.src.database.models.audit import AuditLog
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.maintenance import (
    MaintenanceWorkOrder,
    WorkOrderActivity,
    WorkOrderResolution,
)
from apps.api.src.maintenance.domain.enums import (
    WorkOrderActivityType,
    WorkOrderResolutionStatus,
    WorkOrderStatus,
)
from apps.api.src.maintenance.domain.exceptions import (
    MaintenanceDomainError,
    WorkOrderNotFoundError,
)
from apps.api.src.maintenance.domain.state_machine import validate_status_transition
from apps.api.src.maintenance.infrastructure.repositories import (
    MaintenanceWorkOrderRepository,
    WorkOrderActivityRepository,
    WorkOrderResolutionRepository,
)
from apps.api.src.maintenance.schemas import (
    WorkOrderResolutionCreateRequest,
    WorkOrderResolutionVerifyRequest,
)


class WorkOrderResolutionService:
    """Manages completion, verification, closure, reopening, and linked Phase 10 complaint sync."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.wo_repo = MaintenanceWorkOrderRepository(db)
        self.resolution_repo = WorkOrderResolutionRepository(db)
        self.activity_repo = WorkOrderActivityRepository(db)
        self.complaint_status_service = ComplaintStatusService(db)

    async def complete_work_order(
        self,
        work_order_id: uuid.UUID,
        society_id: uuid.UUID,
        request: WorkOrderResolutionCreateRequest,
        resolver: User,
    ) -> WorkOrderResolution:
        wo = await self.wo_repo.get_by_id(work_order_id, society_id)
        if not wo:
            raise WorkOrderNotFoundError(str(work_order_id))

        validate_status_transition(wo.status, WorkOrderStatus.COMPLETED.value)

        now = datetime.utcnow()
        wo.status = WorkOrderStatus.COMPLETED.value
        wo.resolved_at = now
        wo.actual_end_at = now
        wo.resolution_summary = request.resolution_summary

        await self.wo_repo.update(wo)

        # Check existing resolution or create new
        existing_res = await self.resolution_repo.get_by_work_order(work_order_id, society_id)
        if existing_res:
            resolution = existing_res
            resolution.resolved_by_user_id = resolver.id
            resolution.resolution_summary = request.resolution_summary
            resolution.resolution_code = request.resolution_code
            resolution.resolution_evidence = request.resolution_evidence
            resolution.verification_required = request.verification_required
            resolution.status = WorkOrderResolutionStatus.PENDING_VERIFICATION.value
            resolution.resolved_at = now
        else:
            resolution = WorkOrderResolution(
                society_id=society_id,
                work_order_id=wo.id,
                resolved_by_user_id=resolver.id,
                resolution_summary=request.resolution_summary,
                resolution_code=request.resolution_code,
                resolution_evidence=request.resolution_evidence,
                verification_required=request.verification_required,
                status=WorkOrderResolutionStatus.PENDING_VERIFICATION.value,
                resolved_at=now,
            )
            resolution = await self.resolution_repo.create(resolution)

        activity = WorkOrderActivity(
            society_id=society_id,
            work_order_id=wo.id,
            event_type=WorkOrderActivityType.COMPLETED.value,
            description=f"Work order marked complete: {request.resolution_summary}",
            actor_user_id=resolver.id,
        )
        await self.activity_repo.create(activity)

        audit_entry = AuditLog(
            society_id=society_id,
            actor_user_id=resolver.id,
            action="WORK_ORDER_COMPLETED",
            entity_type="MaintenanceWorkOrder",
            entity_id=str(wo.id),
            after_state={"status": wo.status, "resolution_id": str(resolution.id)},
        )
        self.db.add(audit_entry)

        return resolution

    async def verify_resolution(
        self,
        work_order_id: uuid.UUID,
        society_id: uuid.UUID,
        request: WorkOrderResolutionVerifyRequest,
        verifier: User,
    ) -> WorkOrderResolution:
        wo = await self.wo_repo.get_by_id(work_order_id, society_id)
        if not wo:
            raise WorkOrderNotFoundError(str(work_order_id))

        resolution = await self.resolution_repo.get_by_work_order(work_order_id, society_id)
        if not resolution:
            raise MaintenanceDomainError("No resolution submitted for this work order to verify.")

        now = datetime.utcnow()
        if request.accepted:
            validate_status_transition(wo.status, WorkOrderStatus.VERIFIED.value)
            wo.status = WorkOrderStatus.VERIFIED.value
            resolution.status = WorkOrderResolutionStatus.VERIFIED.value
            resolution.verified_by_user_id = verifier.id
            resolution.verified_at = now
            resolution.verification_comment = request.verification_comment

            await self.wo_repo.update(wo)

            activity_type = WorkOrderActivityType.VERIFIED.value
            activity_desc = "Work order resolution verified and accepted."

            # Phase 10 Complaint Sync: If linked to a complaint, transition linked complaint to RESOLVED cleanly
            if wo.complaint_id:
                try:
                    await self.complaint_status_service.transition_status(
                        society_id=society_id,
                        complaint_id=wo.complaint_id,
                        actor_user_id=verifier.id,
                        target_status="RESOLVED",
                        reason=f"Resolved via Work Order {wo.work_order_number}: {wo.resolution_summary}",
                    )
                except Exception:
                    pass  # Non-blocking sync attempt

        else:
            # Verification rejected -> REOPEN
            validate_status_transition(wo.status, WorkOrderStatus.REOPENED.value)
            wo.status = WorkOrderStatus.REOPENED.value
            resolution.status = WorkOrderResolutionStatus.REJECTED.value
            resolution.verified_by_user_id = verifier.id
            resolution.verified_at = now
            resolution.verification_comment = request.verification_comment

            await self.wo_repo.update(wo)

            activity_type = WorkOrderActivityType.REOPENED.value
            activity_desc = f"Work order resolution rejected and reopened: {request.verification_comment}"

        activity = WorkOrderActivity(
            society_id=society_id,
            work_order_id=wo.id,
            event_type=activity_type,
            description=activity_desc,
            actor_user_id=verifier.id,
        )
        await self.activity_repo.create(activity)

        audit_entry = AuditLog(
            society_id=society_id,
            actor_user_id=verifier.id,
            action="WORK_ORDER_VERIFIED" if request.accepted else "WORK_ORDER_REOPENED",
            entity_type="MaintenanceWorkOrder",
            entity_id=str(wo.id),
            after_state={"status": wo.status, "accepted": request.accepted},
        )
        self.db.add(audit_entry)

        return resolution

    async def close_work_order(
        self, work_order_id: uuid.UUID, society_id: uuid.UUID, closer: User
    ) -> MaintenanceWorkOrder:
        wo = await self.wo_repo.get_by_id(work_order_id, society_id)
        if not wo:
            raise WorkOrderNotFoundError(str(work_order_id))

        validate_status_transition(wo.status, WorkOrderStatus.CLOSED.value)

        wo.status = WorkOrderStatus.CLOSED.value
        wo.closed_at = datetime.utcnow()
        await self.wo_repo.update(wo)

        activity = WorkOrderActivity(
            society_id=society_id,
            work_order_id=wo.id,
            event_type="CLOSED",
            description="Work order closed.",
            actor_user_id=closer.id,
        )
        await self.activity_repo.create(activity)

        audit_entry = AuditLog(
            society_id=society_id,
            actor_user_id=closer.id,
            action="WORK_ORDER_CLOSED",
            entity_type="MaintenanceWorkOrder",
            entity_id=str(wo.id),
            after_state={"status": wo.status},
        )
        self.db.add(audit_entry)

        return wo
