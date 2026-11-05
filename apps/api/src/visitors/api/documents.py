"""API Endpoints for Visitor Photo and Identification Documents."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import (
    require_permission,
    resolve_society_context,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.visitors.application.document_service import VisitorDocumentService
from apps.api.src.visitors.schemas import (
    VisitorDocumentCreateRequest,
    VisitorDocumentResponse,
)

router = APIRouter(tags=["Visitor Documents"])


@router.get("/visitors/{visitor_id}/documents", response_model=list[VisitorDocumentResponse])
async def list_visitor_documents(
    visitor_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("visitor.view")),
) -> list[VisitorDocumentResponse]:
    """List documents/photos for a visitor."""
    service = VisitorDocumentService(db)
    docs = await service.list_documents(society_id, visitor_id)
    return [VisitorDocumentResponse.model_validate(d) for d in docs]


@router.post(
    "/visitors/{visitor_id}/documents",
    response_model=VisitorDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_visitor_document(
    visitor_id: UUID,
    data: VisitorDocumentCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("visitor.create")),
) -> VisitorDocumentResponse:
    """Register document/photo metadata for a visitor."""
    service = VisitorDocumentService(db)
    doc = await service.add_document(society_id, visitor_id, current_user.id, data)
    return VisitorDocumentResponse.model_validate(doc)


@router.delete("/visitors/{visitor_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_visitor_document(
    visitor_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("visitor.manage")),
) -> None:
    """Soft-archive a visitor document."""
    service = VisitorDocumentService(db)
    await service.delete_document(society_id, document_id)
