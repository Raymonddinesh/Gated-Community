"""Vendor Documents API Router."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission, resolve_society_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.vendor.application.document_service import VendorDocumentService
from apps.api.src.vendor.schemas import VendorDocumentCreate, VendorDocumentResponse

router = APIRouter(prefix="", tags=["Vendor Documents"])


@router.post(
    "/{vendor_id}/documents",
    response_model=VendorDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("vendor.document.manage"))],
)
async def upload_vendor_document(
    vendor_id: UUID,
    payload: VendorDocumentCreate,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    storage_key = f"vendors/{society_id}/{vendor_id}/{payload.original_filename}"
    doc_service = VendorDocumentService(db)
    return await doc_service.upload_document(
        vendor_id=vendor_id,
        data=payload,
        storage_key=storage_key,
        society_id=society_id,
        current_user_id=current_user.id,
    )


@router.get(
    "/{vendor_id}/documents",
    response_model=list[VendorDocumentResponse],
    dependencies=[Depends(require_permission("vendor.document.view"))],
)
async def list_vendor_documents(
    vendor_id: UUID,
    include_archived: bool = Query(False),
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    doc_service = VendorDocumentService(db)
    return await doc_service.list_documents(vendor_id, society_id, include_archived=include_archived)


@router.delete(
    "/documents/{document_id}",
    response_model=VendorDocumentResponse,
    dependencies=[Depends(require_permission("vendor.document.manage"))],
)
async def archive_vendor_document(
    document_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    doc_service = VendorDocumentService(db)
    return await doc_service.archive_document(document_id, society_id)
