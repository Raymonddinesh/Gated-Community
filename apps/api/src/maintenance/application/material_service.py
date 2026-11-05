"""Application Service for Work Order Material Usage Tracking (Operational tracker, Non-financial)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.audit import AuditLog
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.maintenance import WorkOrderActivity, WorkOrderMaterialUsage
from apps.api.src.maintenance.domain.enums import WorkOrderActivityType
from apps.api.src.maintenance.domain.exceptions import WorkOrderNotFoundError
from apps.api.src.maintenance.infrastructure.repositories import (
    MaintenanceWorkOrderRepository,
    WorkOrderActivityRepository,
    WorkOrderMaterialUsageRepository,
)
from apps.api.src.maintenance.schemas import WorkOrderMaterialUsageCreateRequest


class WorkOrderMaterialService:
    """Manages operational material and parts usage tracking without financial ledger mutations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.wo_repo = MaintenanceWorkOrderRepository(db)
        self.material_repo = WorkOrderMaterialUsageRepository(db)
        self.activity_repo = WorkOrderActivityRepository(db)

    async def add_material_usage(
        self,
        work_order_id: uuid.UUID,
        society_id: uuid.UUID,
        request: WorkOrderMaterialUsageCreateRequest,
        creator: User,
    ) -> WorkOrderMaterialUsage:
        wo = await self.wo_repo.get_by_id(work_order_id, society_id)
        if not wo:
            raise WorkOrderNotFoundError(str(work_order_id))

        material = WorkOrderMaterialUsage(
            society_id=society_id,
            work_order_id=wo.id,
            material_name=request.material_name,
            description=request.description,
            quantity=request.quantity,
            unit=request.unit,
            estimated_unit_cost=request.estimated_unit_cost,
            actual_unit_cost=request.actual_unit_cost,
            notes=request.notes,
            created_by_user_id=creator.id,
        )
        material = await self.material_repo.create(material)

        activity = WorkOrderActivity(
            society_id=society_id,
            work_order_id=wo.id,
            event_type=WorkOrderActivityType.PART_ADDED.value,
            description=f"Material '{request.material_name}' ({request.quantity} {request.unit}) added.",
            actor_user_id=creator.id,
        )
        await self.activity_repo.create(activity)

        audit_entry = AuditLog(
            society_id=society_id,
            actor_user_id=creator.id,
            action="WORK_ORDER_MATERIAL_ADDED",
            entity_type="WorkOrderMaterialUsage",
            entity_id=str(material.id),
            after_state={"material_name": request.material_name, "quantity": str(request.quantity)},
        )
        self.db.add(audit_entry)

        return material

    async def list_materials(
        self, work_order_id: uuid.UUID, society_id: uuid.UUID
    ) -> list[WorkOrderMaterialUsage]:
        wo = await self.wo_repo.get_by_id(work_order_id, society_id)
        if not wo:
            raise WorkOrderNotFoundError(str(work_order_id))

        return await self.material_repo.list_by_work_order(work_order_id, society_id)
