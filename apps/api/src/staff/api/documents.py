"""API Router for Staff Documents."""

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, resolve_society_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.session import get_db_session
from apps.api.src.staff.application.document_service import StaffDocumentService
from apps.api.src.staff.domain.enums import StaffDocumentType
from apps.api.src.staff.schemas import StaffDocumentResponse

router = APIRouter(prefix="/documents", tags=["Staff Documents"])


@router.post("/upload", response_model=StaffDocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    staff_id: uuid.UUID = Form(...),
    document_type: StaffDocumentType = Form(StaffDocumentType.IDENTITY),
    file: UploadFile = File(...),
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> StaffDocumentResponse:
    """Upload staff document with MIME and size validation."""
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "staff.document.manage" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to manage staff documents.")

    content = await file.read()
    service = StaffDocumentService(db)
    doc = await service.upload_document(
        staff_id=staff_id,
        society_id=society_id,
        original_filename=file.filename or "file",
        content_type=file.content_type or "application/octet-stream",
        file_bytes=content,
        document_type=document_type,
        uploaded_by_user=current_user,
    )
    return StaffDocumentResponse.model_validate(doc)


@router.get("", response_model=list[StaffDocumentResponse])
async def list_documents(
    staff_id: uuid.UUID,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[StaffDocumentResponse]:
    """List staff document metadata."""
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "staff.document.view" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to read staff documents.")

    service = StaffDocumentService(db)
    docs = await service.list_documents(staff_id, society_id)
    return [StaffDocumentResponse.model_validate(d) for d in docs]


@router.post("/{document_id}/archive", response_model=StaffDocumentResponse)
async def archive_document(
    document_id: uuid.UUID,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> StaffDocumentResponse:
    """Soft-archive staff document."""
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "staff.document.manage" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to archive staff documents.")

    service = StaffDocumentService(db)
    doc = await service.archive_document(document_id, society_id)
    return StaffDocumentResponse.model_validate(doc)
