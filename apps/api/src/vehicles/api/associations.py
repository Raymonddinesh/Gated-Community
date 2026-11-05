"""API endpoints for Vehicle-Resident Associations."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import (
    require_permission,
    resolve_society_context,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.vehicles.application.association_service import VehicleAssociationService
from apps.api.src.vehicles.schemas import (
    VehicleAssociationCreateRequest,
    VehicleAssociationResponse,
)

router = APIRouter(tags=["Vehicle Associations"])


@router.post(
    "/vehicles/{vehicle_id}/associations", response_model=VehicleAssociationResponse, status_code=201
)
async def add_vehicle_association(
    vehicle_id: UUID,
    data: VehicleAssociationCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("vehicle.update")),
) -> VehicleAssociationResponse:
    """Associate a vehicle with a resident user and unit."""
    service = VehicleAssociationService(db)
    assoc = await service.add_association(society_id, vehicle_id, current_user.id, data)
    return VehicleAssociationResponse.model_validate(assoc)


@router.delete(
    "/vehicles/{vehicle_id}/associations/{association_id}", response_model=VehicleAssociationResponse
)
async def end_vehicle_association(
    vehicle_id: UUID,
    association_id: UUID,
    notes: str | None = Query(None, description="Reason for ending association"),
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("vehicle.update")),
) -> VehicleAssociationResponse:
    """End a vehicle association with a resident/unit."""
    service = VehicleAssociationService(db)
    assoc = await service.end_association(society_id, association_id, current_user.id, notes)
    return VehicleAssociationResponse.model_validate(assoc)


@router.post(
    "/vehicles/{vehicle_id}/associations/{association_id}/primary",
    response_model=VehicleAssociationResponse,
)
async def set_primary_vehicle_association(
    vehicle_id: UUID,
    association_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("vehicle.update")),
) -> VehicleAssociationResponse:
    """Designate an association as the primary vehicle for the resident and unit."""
    service = VehicleAssociationService(db)
    assoc = await service.set_primary(society_id, association_id, current_user.id)
    return VehicleAssociationResponse.model_validate(assoc)
