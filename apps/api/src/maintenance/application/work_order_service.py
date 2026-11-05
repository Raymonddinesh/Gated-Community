"""Application Service for Maintenance Work Order Core Lifecycle."""

import json
import uuid
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.complaints.infrastructure.repositories import ComplaintRepository
from apps.api.src.database.models.audit import AuditLog
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.maintenance import (
    MaintenanceWorkOrder,
    WorkOrderActivity,
    WorkOrderStatusHistory,
)
from apps.api.src.maintenance.domain.enums import (
    WorkOrderActivityType,
    WorkOrderPriority,
    WorkOrderStatus,
)
from apps.api.src.maintenance.domain.exceptions import (
    CrossSocietyWorkOrderError,
    InvalidScheduleError,
    MaintenanceCategoryNotFoundError,
    WorkOrderNotFoundError,
)
from apps.api.src.maintenance.domain.state_machine import validate_status_transition
from apps.api.src.maintenance.infrastructure.repositories import (
    MaintenanceCategoryRepository,
    MaintenanceWorkOrderRepository,
    WorkOrderActivityRepository,
)
from apps.api.src.maintenance.schemas import (
    WorkOrderCreateRequest,
    WorkOrderScheduleRequest,
    WorkOrderStatusUpdateRequest,
)


class MaintenanceWorkOrderService:
    """Core Application Service managing work order creation, scheduling, and lifecycle transitions."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.category_repo = MaintenanceCategoryRepository(db)
        self.wo_repo = MaintenanceWorkOrderRepository(db)
        self.activity_repo = WorkOrderActivityRepository(db)
        self.complaint_repo = ComplaintRepository(db)

    async def create_work_order(
        self,
        request: WorkOrderCreateRequest,
        society_id: uuid.UUID,
        creator: User,
    ) -> MaintenanceWorkOrder:
        # 1. Validate Category & Subcategory
        category = await self.category_repo.get_category_by_id(request.category_id, society_id)
        if not category or not category.is_active:
            raise MaintenanceCategoryNotFoundError(str(request.category_id))

        if request.subcategory_id:
            subcategory = await self.category_repo.get_subcategory_by_id(request.subcategory_id, society_id)
            if not subcategory or subcategory.category_id != category.id:
                raise CrossSocietyWorkOrderError("Subcategory does not belong to category or society.")

        # 2. Validate Complaint Linkage (Phase 10 Integration)
        if request.complaint_id:
            complaint = await self.complaint_repo.get_by_id(request.complaint_id, society_id)
            if not complaint:
                raise CrossSocietyWorkOrderError("Linked complaint not found or belongs to another society.")

        # 3. Schedule timestamp validation
        if request.scheduled_start_at and request.scheduled_end_at:
            if request.scheduled_end_at <= request.scheduled_start_at:
                raise InvalidScheduleError("Scheduled end time must be after scheduled start time.")

        # 4. Generate Work Order Number
        wo_number = await self.wo_repo.generate_next_work_order_number(society_id)

        # 5. Calculate default due_at based on priority
        due_hours = {
            WorkOrderPriority.CRITICAL: 12,
            WorkOrderPriority.HIGH: 24,
            WorkOrderPriority.MEDIUM: 72,
            WorkOrderPriority.LOW: 168,
        }.get(request.priority, 72)
        due_at = datetime.utcnow() + timedelta(hours=due_hours)

        # 6. Instantiate Work Order Model
        wo = MaintenanceWorkOrder(
            society_id=society_id,
            work_order_number=wo_number,
            title=request.title,
            description=request.description,
            category_id=category.id,
            subcategory_id=request.subcategory_id,
            source=request.source.value,
            complaint_id=request.complaint_id,
            unit_id=request.unit_id,
            block_id=request.block_id,
            priority=request.priority.value,
            status=WorkOrderStatus.OPEN.value,
            requested_by_user_id=creator.id,
            requested_for_unit_id=request.requested_for_unit_id,
            vehicle_id=request.vehicle_id,
            visitor_id=request.visitor_id,
            created_by_user_id=creator.id,
            due_at=due_at,
            scheduled_start_at=request.scheduled_start_at,
            scheduled_end_at=request.scheduled_end_at,
        )

        wo = await self.wo_repo.create(wo)

        # 7. Log Activity Timeline
        activity = WorkOrderActivity(
            society_id=society_id,
            work_order_id=wo.id,
            event_type=WorkOrderActivityType.CREATED.value,
            description=f"Work Order {wo.work_order_number} created.",
            actor_user_id=creator.id,
        )
        await self.activity_repo.create(activity)

        # 8. Core Audit Log
        audit_entry = AuditLog(
            society_id=society_id,
            actor_user_id=creator.id,
            action="WORK_ORDER_CREATED",
            entity_type="MaintenanceWorkOrder",
            entity_id=str(wo.id),
            after_state={"work_order_number": wo.work_order_number, "priority": wo.priority},
        )
        self.db.add(audit_entry)

        return await self.wo_repo.get_by_id(wo.id, society_id)  # type: ignore[return-value]

    async def get_work_order(
        self, work_order_id: uuid.UUID, society_id: uuid.UUID, caller: User, has_view_all: bool
    ) -> MaintenanceWorkOrder:
        wo = await self.wo_repo.get_by_id(work_order_id, society_id)
        if not wo:
            raise WorkOrderNotFoundError(str(work_order_id))

        if not has_view_all and wo.requested_by_user_id != caller.id and wo.created_by_user_id != caller.id:
            raise WorkOrderNotFoundError(str(work_order_id))

        return wo

    async def list_work_orders(
        self,
        society_id: uuid.UUID,
        caller: User,
        has_view_all: bool,
        status: str | None = None,
        priority: str | None = None,
        category_id: uuid.UUID | None = None,
        complaint_id: uuid.UUID | None = None,
        is_overdue: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MaintenanceWorkOrder], int]:
        requested_by_filter = None if has_view_all else caller.id

        return await self.wo_repo.list_work_orders(
            society_id=society_id,
            status=status,
            priority=priority,
            category_id=category_id,
            requested_by_user_id=requested_by_filter,
            complaint_id=complaint_id,
            is_overdue=is_overdue,
            limit=limit,
            offset=offset,
        )

    async def update_schedule(
        self,
        work_order_id: uuid.UUID,
        society_id: uuid.UUID,
        request: WorkOrderScheduleRequest,
        updater: User,
    ) -> MaintenanceWorkOrder:
        wo = await self.wo_repo.get_by_id(work_order_id, society_id)
        if not wo:
            raise WorkOrderNotFoundError(str(work_order_id))

        if request.scheduled_end_at <= request.scheduled_start_at:
            raise InvalidScheduleError("Scheduled end time must be after scheduled start time.")

        wo.scheduled_start_at = request.scheduled_start_at
        wo.scheduled_end_at = request.scheduled_end_at
        if request.estimated_start_at:
            wo.estimated_start_at = request.estimated_start_at

        # Transition status to SCHEDULED if currently OPEN or ASSIGNED
        if wo.status in [WorkOrderStatus.OPEN.value, WorkOrderStatus.ASSIGNED.value]:
            validate_status_transition(wo.status, WorkOrderStatus.SCHEDULED.value)
            wo.status = WorkOrderStatus.SCHEDULED.value

        await self.wo_repo.update(wo)

        activity = WorkOrderActivity(
            society_id=society_id,
            work_order_id=wo.id,
            event_type=WorkOrderActivityType.SCHEDULED.value,
            description=f"Work Order scheduled from {request.scheduled_start_at} to {request.scheduled_end_at}.",
            actor_user_id=updater.id,
        )
        await self.activity_repo.create(activity)

        return wo

    async def transition_status(
        self,
        work_order_id: uuid.UUID,
        society_id: uuid.UUID,
        request: WorkOrderStatusUpdateRequest,
        updater: User,
    ) -> MaintenanceWorkOrder:
        wo = await self.wo_repo.get_by_id(work_order_id, society_id)
        if not wo:
            raise WorkOrderNotFoundError(str(work_order_id))

        from_status = wo.status
        to_status = request.status.value

        validate_status_transition(from_status, to_status)

        wo.status = to_status
        now = datetime.utcnow()

        if to_status == WorkOrderStatus.IN_PROGRESS.value and not wo.actual_start_at:
            wo.actual_start_at = now
        elif to_status == WorkOrderStatus.CANCELLED.value:
            wo.cancelled_at = now
        elif to_status == WorkOrderStatus.CLOSED.value:
            wo.closed_at = now

        await self.wo_repo.update(wo)

        # Record Status History
        history = WorkOrderStatusHistory(
            society_id=society_id,
            work_order_id=wo.id,
            from_status=from_status,
            to_status=to_status,
            changed_by_user_id=updater.id,
            reason=request.reason,
        )
        self.db.add(history)

        activity = WorkOrderActivity(
            society_id=society_id,
            work_order_id=wo.id,
            event_type=WorkOrderActivityType.STATUS_CHANGED.value,
            description=f"Status changed from {from_status} to {to_status}.",
            actor_user_id=updater.id,
            metadata_json=json.dumps({"reason": request.reason}),
        )
        await self.activity_repo.create(activity)

        audit_entry = AuditLog(
            society_id=society_id,
            actor_user_id=updater.id,
            action="WORK_ORDER_STATUS_CHANGED",
            entity_type="MaintenanceWorkOrder",
            entity_id=str(wo.id),
            before_state={"status": from_status},
            after_state={"status": to_status},
        )
        self.db.add(audit_entry)

        return wo
