"""Application Service for Work Order SLA Escalations."""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.audit import AuditLog
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.maintenance import WorkOrderActivity, WorkOrderEscalation
from apps.api.src.maintenance.domain.enums import WorkOrderActivityType
from apps.api.src.maintenance.domain.exceptions import WorkOrderNotFoundError
from apps.api.src.maintenance.infrastructure.repositories import (
    MaintenanceWorkOrderRepository,
    WorkOrderActivityRepository,
    WorkOrderEscalationRepository,
)


class WorkOrderEscalationService:
    """Manages SLA breach detection and idempotent escalation logging."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.wo_repo = MaintenanceWorkOrderRepository(db)
        self.escalation_repo = WorkOrderEscalationRepository(db)
        self.activity_repo = WorkOrderActivityRepository(db)

    async def trigger_escalation(
        self,
        work_order_id: uuid.UUID,
        society_id: uuid.UUID,
        reason: str,
        trigger_user: User | None = None,
    ) -> WorkOrderEscalation:
        wo = await self.wo_repo.get_by_id(work_order_id, society_id)
        if not wo:
            raise WorkOrderNotFoundError(str(work_order_id))

        # Idempotency check: Return active escalation if one is already pending
        existing = await self.escalation_repo.get_active_escalation(work_order_id, society_id)
        if existing:
            return existing

        escalation = WorkOrderEscalation(
            society_id=society_id,
            work_order_id=wo.id,
            escalation_level=1,
            reason=reason,
            status="PENDING",
            triggered_at=datetime.utcnow(),
            triggered_by_user_id=trigger_user.id if trigger_user else None,
        )
        escalation = await self.escalation_repo.create(escalation)

        activity = WorkOrderActivity(
            society_id=society_id,
            work_order_id=wo.id,
            event_type=WorkOrderActivityType.ESCALATED.value,
            description=f"SLA Escalation triggered: {reason}",
            actor_user_id=trigger_user.id if trigger_user else None,
        )
        await self.activity_repo.create(activity)

        audit_entry = AuditLog(
            society_id=society_id,
            actor_user_id=trigger_user.id if trigger_user else None,
            action="WORK_ORDER_ESCALATED",
            entity_type="WorkOrderEscalation",
            entity_id=str(escalation.id),
            after_state={"reason": reason, "work_order_id": str(wo.id)},
        )
        self.db.add(audit_entry)

        return escalation
