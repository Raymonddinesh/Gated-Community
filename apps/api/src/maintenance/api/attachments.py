"""API Router for Work Order Attachments."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, resolve_society_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.maintenance import WorkOrderAttachment
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.session import get_db_session
from apps.api.src.maintenance.application.attachment_service import WorkOrderAttachmentService
from apps.api.src.maintenance.domain.enums import WorkOrderFileType
from apps.api.src.maintenance.schemas import WorkOrderAttachmentResponse

router = APIRouter(prefix="/work-orders/{work_order_id}/attachments", tags=["Work Order Attachments"])


@router.get("", response_model=list[WorkOrderAttachmentResponse])
async def list_attachments(
    work_order_id: uuid.UUID,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[WorkOrderAttachment]:
    service = WorkOrderAttachmentService(db)
    return await service.list_attachments(work_order_id, society_id)


@router.post("", response_model=WorkOrderAttachmentResponse, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    work_order_id: uuid.UUID,
    file_name: str,
    file_size: int,
    mime_type: str,
    file_type: WorkOrderFileType = WorkOrderFileType.PHOTO,
    storage_key: str = "mock/storage/key",
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> WorkOrderAttachment:
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "maintenance.attachment.manage" not in perms and "maintenance.create" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to upload attachments.")

    service = WorkOrderAttachmentService(db)
    return await service.register_attachment(
        work_order_id=work_order_id,
        society_id=society_id,
        uploader=current_user,
        file_name=file_name,
        file_size=file_size,
        mime_type=mime_type,
        file_type=file_type,
        storage_key=storage_key,
    )
