"""Application Service for Work Order Attachments."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.audit import AuditLog
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.maintenance import WorkOrderActivity, WorkOrderAttachment
from apps.api.src.maintenance.domain.enums import WorkOrderActivityType, WorkOrderFileType
from apps.api.src.maintenance.domain.exceptions import (
    MaintenanceDomainError,
    WorkOrderNotFoundError,
)
from apps.api.src.maintenance.infrastructure.repositories import (
    MaintenanceWorkOrderRepository,
    WorkOrderActivityRepository,
    WorkOrderAttachmentRepository,
)

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
    "audio/mpeg",
    "audio/wav",
    "video/mp4",
}
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB Limit


class WorkOrderAttachmentService:
    """Manages file attachments, MIME validation, and evidence security for work orders."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.wo_repo = MaintenanceWorkOrderRepository(db)
        self.attachment_repo = WorkOrderAttachmentRepository(db)
        self.activity_repo = WorkOrderActivityRepository(db)

    async def register_attachment(
        self,
        work_order_id: uuid.UUID,
        society_id: uuid.UUID,
        uploader: User,
        file_name: str,
        file_size: int,
        mime_type: str,
        file_type: WorkOrderFileType,
        storage_key: str,
    ) -> WorkOrderAttachment:
        wo = await self.wo_repo.get_by_id(work_order_id, society_id)
        if not wo:
            raise WorkOrderNotFoundError(str(work_order_id))

        if mime_type not in ALLOWED_MIME_TYPES:
            raise MaintenanceDomainError(f"MIME type '{mime_type}' is not permitted.")

        if file_size > MAX_FILE_SIZE_BYTES:
            raise MaintenanceDomainError("File size exceeds maximum permitted limit of 25MB.")

        attachment = WorkOrderAttachment(
            society_id=society_id,
            work_order_id=wo.id,
            uploaded_by_user_id=uploader.id,
            file_name=file_name,
            file_type=file_type.value,
            file_size=file_size,
            storage_key=storage_key,
            mime_type=mime_type,
        )
        attachment = await self.attachment_repo.create(attachment)

        activity = WorkOrderActivity(
            society_id=society_id,
            work_order_id=wo.id,
            event_type=WorkOrderActivityType.ATTACHMENT_ADDED.value,
            description=f"Attachment '{file_name}' uploaded.",
            actor_user_id=uploader.id,
        )
        await self.activity_repo.create(activity)

        audit_entry = AuditLog(
            society_id=society_id,
            actor_user_id=uploader.id,
            action="WORK_ORDER_ATTACHMENT_UPLOADED",
            entity_type="WorkOrderAttachment",
            entity_id=str(attachment.id),
            after_state={"file_name": file_name, "mime_type": mime_type},
        )
        self.db.add(audit_entry)

        return attachment

    async def list_attachments(
        self, work_order_id: uuid.UUID, society_id: uuid.UUID
    ) -> list[WorkOrderAttachment]:
        wo = await self.wo_repo.get_by_id(work_order_id, society_id)
        if not wo:
            raise WorkOrderNotFoundError(str(work_order_id))

        return await self.attachment_repo.list_by_work_order(work_order_id, society_id)
