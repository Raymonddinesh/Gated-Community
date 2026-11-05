"""API Router for Complaint Attachments."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import (
    require_permission,
    resolve_society_context,
)
from apps.api.src.complaints.application.attachment_service import ComplaintAttachmentService
from apps.api.src.complaints.schemas import (
    ComplaintAttachmentCreateRequest,
    ComplaintAttachmentResponse,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session

router = APIRouter(tags=["Complaint Attachments"])


@router.post(
    "/complaints/{complaint_id}/attachments",
    response_model=ComplaintAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    complaint_id: UUID,
    data: ComplaintAttachmentCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("complaint.create")),
) -> ComplaintAttachmentResponse:
    """Register metadata for a complaint attachment."""
    service = ComplaintAttachmentService(db)
    attachment = await service.add_attachment(
        society_id=society_id,
        complaint_id=complaint_id,
        uploaded_by_user_id=current_user.id,
        data=data,
    )
    return ComplaintAttachmentResponse.model_validate(attachment)


@router.get(
    "/complaints/{complaint_id}/attachments",
    response_model=list[ComplaintAttachmentResponse],
)
async def list_attachments(
    complaint_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("complaint.create")),
) -> list[ComplaintAttachmentResponse]:
    """List active attachments for a complaint."""
    service = ComplaintAttachmentService(db)
    attachments = await service.list_attachments(society_id, complaint_id)
    return [ComplaintAttachmentResponse.model_validate(a) for a in attachments]


@router.delete(
    "/complaints/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@router.delete(
    "/complaints/{complaint_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def archive_attachment(
    attachment_id: UUID,
    complaint_id: UUID | None = None,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("complaint.attachment.manage")),
) -> None:
    """Soft-archive a complaint attachment."""
    service = ComplaintAttachmentService(db)
    await service.archive_attachment(society_id, attachment_id, current_user.id)
