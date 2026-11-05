"""API endpoints for Vehicle Documents."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import (
    require_permission,
    resolve_society_context,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.vehicles.application.document_service import VehicleDocumentService
from apps.api.src.vehicles.schemas import (
    VehicleDocumentCreateRequest,
    VehicleDocumentResponse,
)

router = APIRouter(tags=["Vehicle Documents"])


@router.get("/vehicles/{vehicle_id}/documents", response_model=list[VehicleDocumentResponse])
async def list_vehicle_documents(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("vehicle.document.view")),
) -> list[VehicleDocumentResponse]:
    """List documents for a vehicle."""
    service = VehicleDocumentService(db)
    docs = await service.list_documents(society_id, vehicle_id)
    return [VehicleDocumentResponse.model_validate(d) for d in docs]


@router.post(
    "/vehicles/{vehicle_id}/documents",
    response_model=VehicleDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_vehicle_document(
    vehicle_id: UUID,
    data: VehicleDocumentCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("vehicle.document.manage")),
) -> VehicleDocumentResponse:
    """Upload / register document metadata for a vehicle."""
    service = VehicleDocumentService(db)
    doc = await service.add_document(society_id, vehicle_id, current_user.id, data)
    return VehicleDocumentResponse.model_validate(doc)


@router.delete("/vehicles/{vehicle_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vehicle_document(
    vehicle_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("vehicle.document.manage")),
) -> None:
    """Delete a vehicle document reference."""
    service = VehicleDocumentService(db)
    await service.delete_document(society_id, document_id)
