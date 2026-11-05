"""Application Service for Work Order Comments."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.audit import AuditLog
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.maintenance import WorkOrderActivity, WorkOrderComment
from apps.api.src.maintenance.domain.enums import WorkOrderActivityType, WorkOrderCommentType
from apps.api.src.maintenance.domain.exceptions import (
    WorkOrderNotFoundError,
    WorkOrderPermissionDeniedError,
)
from apps.api.src.maintenance.infrastructure.repositories import (
    MaintenanceWorkOrderRepository,
    WorkOrderActivityRepository,
    WorkOrderCommentRepository,
)
from apps.api.src.maintenance.schemas import WorkOrderCommentCreateRequest


class WorkOrderCommentService:
    """Manages public and internal comments for work orders."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.wo_repo = MaintenanceWorkOrderRepository(db)
        self.comment_repo = WorkOrderCommentRepository(db)
        self.activity_repo = WorkOrderActivityRepository(db)

    async def add_comment(
        self,
        work_order_id: uuid.UUID,
        society_id: uuid.UUID,
        request: WorkOrderCommentCreateRequest,
        author: User,
        has_internal_perm: bool,
    ) -> WorkOrderComment:
        wo = await self.wo_repo.get_by_id(work_order_id, society_id)
        if not wo:
            raise WorkOrderNotFoundError(str(work_order_id))

        if request.comment_type == WorkOrderCommentType.INTERNAL and not has_internal_perm:
            raise WorkOrderPermissionDeniedError("Only authorized staff may post internal comments.")

        is_internal = request.comment_type == WorkOrderCommentType.INTERNAL

        comment = WorkOrderComment(
            society_id=society_id,
            work_order_id=wo.id,
            user_id=author.id,
            comment_text=request.comment_text,
            comment_type=request.comment_type.value,
            is_internal=is_internal,
        )
        comment = await self.comment_repo.create(comment)

        activity = WorkOrderActivity(
            society_id=society_id,
            work_order_id=wo.id,
            event_type=WorkOrderActivityType.COMMENT_ADDED.value,
            description=f"Comment added by user ({request.comment_type.value}).",
            actor_user_id=author.id,
        )
        await self.activity_repo.create(activity)

        audit_entry = AuditLog(
            society_id=society_id,
            actor_user_id=author.id,
            action="WORK_ORDER_COMMENT_ADDED",
            entity_type="WorkOrderComment",
            entity_id=str(comment.id),
            after_state={"work_order_id": str(wo.id), "is_internal": is_internal},
        )
        self.db.add(audit_entry)

        return comment

    async def list_comments(
        self,
        work_order_id: uuid.UUID,
        society_id: uuid.UUID,
        caller: User,
        has_internal_perm: bool,
    ) -> list[WorkOrderComment]:
        wo = await self.wo_repo.get_by_id(work_order_id, society_id)
        if not wo:
            raise WorkOrderNotFoundError(str(work_order_id))

        return await self.comment_repo.list_by_work_order(
            work_order_id, society_id, include_internal=has_internal_perm
        )
