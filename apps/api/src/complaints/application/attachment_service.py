"""Application Service for Complaint Attachments and Evidence Uploads."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.complaints.domain.exceptions import (
    ComplaintAttachmentError,
    ComplaintNotFoundError,
)
from apps.api.src.complaints.infrastructure.repositories import (
    ComplaintAttachmentRepository,
    ComplaintRepository,
)
from apps.api.src.complaints.schemas import ComplaintAttachmentCreateRequest
from apps.api.src.database.models.audit import AuditLog
from apps.api.src.database.models.complaint import ComplaintAttachment


class ComplaintAttachmentService:
    """Service managing metadata and object storage references for complaint evidence attachments."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.complaint_repo = ComplaintRepository(session)
        self.attachment_repo = ComplaintAttachmentRepository(session)

    async def add_attachment(
        self,
        society_id: uuid.UUID,
        complaint_id: uuid.UUID,
        uploaded_by_user_id: uuid.UUID,
        data: ComplaintAttachmentCreateRequest,
    ) -> ComplaintAttachment:
        """Register attachment metadata for a complaint."""
        complaint = await self.complaint_repo.get_by_id(complaint_id, society_id)
        if not complaint:
            raise ComplaintNotFoundError(complaint_id)

        # Basic key security validation
        file_key_clean = data.file_key.strip()
        if ".." in file_key_clean or file_key_clean.startswith("/"):
            raise ComplaintAttachmentError("Path traversal in file_key is forbidden")

        now = datetime.now(UTC)
        attachment = ComplaintAttachment(
            id=uuid.uuid4(),
            society_id=society_id,
            complaint_id=complaint_id,
            uploaded_by_user_id=uploaded_by_user_id,
            attachment_type=data.attachment_type.value,
            file_key=file_key_clean,
            original_filename=data.original_filename.strip(),
            content_type=data.content_type.strip(),
            file_size_bytes=data.file_size_bytes,
            checksum=data.checksum.strip() if data.checksum else None,
            created_at=now,
        )
        await self.attachment_repo.save(attachment)

        # Audit event
        audit = AuditLog(
            id=uuid.uuid4(),
            society_id=society_id,
            actor_user_id=uploaded_by_user_id,
            action="complaint.attachment.add",
            entity_type="ComplaintAttachment",
            entity_id=str(attachment.id),
            after_state={
                "complaint_id": str(complaint_id),
                "attachment_type": data.attachment_type.value,
                "original_filename": data.original_filename,
            },
        )
        self.session.add(audit)
        await self.session.flush()

        return attachment

    async def list_attachments(
        self,
        society_id: uuid.UUID,
        complaint_id: uuid.UUID,
    ) -> list[ComplaintAttachment]:
        complaint = await self.complaint_repo.get_by_id(complaint_id, society_id)
        if not complaint:
            raise ComplaintNotFoundError(complaint_id)
        return await self.attachment_repo.list_for_complaint(society_id, complaint_id)

    async def archive_attachment(
        self,
        society_id: uuid.UUID,
        attachment_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        attachment = await self.attachment_repo.get_by_id(attachment_id, society_id)
        if not attachment:
            raise ComplaintAttachmentError(f"Attachment '{attachment_id}' not found")

        await self.attachment_repo.delete(attachment)

        # Audit event
        audit = AuditLog(
            id=uuid.uuid4(),
            society_id=society_id,
            actor_user_id=user_id,
            action="complaint.attachment.archive",
            entity_type="ComplaintAttachment",
            entity_id=str(attachment_id),
            after_state={
                "complaint_id": str(attachment.complaint_id),
            },
        )
        self.session.add(audit)
        await self.session.flush()
