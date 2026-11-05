"""Unit Occupancy, Move-In, and Move-Out API Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import (
    require_permission,
    resolve_society_context,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.residents.application.occupancy_service import OccupancyService
from apps.api.src.residents.schemas import (
    UnitOccupancyCreate,
    UnitOccupancyEndRequest,
    UnitOccupancyResponse,
    UnitOccupancyUpdate,
)

router = APIRouter(tags=["Occupancy"])


@router.get("/units/{unit_id}/occupants", response_model=list[UnitOccupancyResponse])
async def list_unit_occupants(
    unit_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("occupancy.read")),
) -> list[UnitOccupancyResponse]:
    """List current active occupants of a unit."""
    service = OccupancyService(db)
    return await service.list_occupants(society_id, unit_id)


@router.get("/units/{unit_id}/occupancy-history", response_model=list[UnitOccupancyResponse])
async def get_unit_occupancy_history(
    unit_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("occupancy.read")),
) -> list[UnitOccupancyResponse]:
    """Retrieve full historical and active occupancy records for a unit."""
    service = OccupancyService(db)
    return await service.get_occupancy_history(society_id, unit_id)


@router.post("/units/{unit_id}/occupancies", response_model=UnitOccupancyResponse)
async def create_unit_occupancy(
    unit_id: UUID,
    data: UnitOccupancyCreate,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("occupancy.manage")),
) -> UnitOccupancyResponse:
    """Move-in / create new unit occupancy with tenant overlap prevention."""
    service = OccupancyService(db)
    return await service.move_in(society_id, unit_id, data, current_user.id)


@router.patch("/occupancies/{occupancy_id}", response_model=UnitOccupancyResponse)
async def update_occupancy(
    occupancy_id: UUID,
    data: UnitOccupancyUpdate,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("occupancy.manage")),
) -> UnitOccupancyResponse:
    """Update occupancy details."""
    service = OccupancyService(db)
    return await service.update_occupancy(society_id, occupancy_id, data, current_user.id)


@router.post("/occupancies/{occupancy_id}/end", response_model=UnitOccupancyResponse)
async def end_unit_occupancy(
    occupancy_id: UUID,
    data: UnitOccupancyEndRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("occupancy.manage")),
) -> UnitOccupancyResponse:
    """Move-out / end an occupancy while preserving historical records."""
    service = OccupancyService(db)
    return await service.move_out(society_id, occupancy_id, data, current_user.id)
