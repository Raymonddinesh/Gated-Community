"""Unit Ownership and Joint Co-Owner API Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import (
    require_permission,
    resolve_society_context,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.residents.application.ownership_service import OwnershipService
from apps.api.src.residents.schemas import (
    UnitOwnershipCreate,
    UnitOwnershipEndRequest,
    UnitOwnershipResponse,
    UnitOwnershipTransferRequest,
    UnitOwnershipTransferResponse,
    UnitOwnershipUpdate,
)

router = APIRouter(tags=["Ownership"])


@router.get("/units/{unit_id}/owners", response_model=list[UnitOwnershipResponse])
async def list_unit_owners(
    unit_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("units.read")),
) -> list[UnitOwnershipResponse]:
    """List current active owners and joint co-owners for a unit."""
    service = OwnershipService(db)
    return await service.list_owners(society_id, unit_id)


@router.get("/units/{unit_id}/ownership-history", response_model=list[UnitOwnershipResponse])
async def get_unit_ownership_history(
    unit_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("units.read")),
) -> list[UnitOwnershipResponse]:
    """Retrieve full historical and active ownership records for a unit."""
    service = OwnershipService(db)
    return await service.get_ownership_history(society_id, unit_id)


@router.post("/units/{unit_id}/owners", response_model=UnitOwnershipResponse)
async def add_unit_owner(
    unit_id: UUID,
    data: UnitOwnershipCreate,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("units.manage")),
) -> UnitOwnershipResponse:
    """Add owner or joint co-owner to a unit with percentage validation."""
    service = OwnershipService(db)
    return await service.add_owner(society_id, unit_id, data, current_user.id)


@router.patch("/ownerships/{ownership_id}", response_model=UnitOwnershipResponse)
async def update_ownership(
    ownership_id: UUID,
    data: UnitOwnershipUpdate,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("units.manage")),
) -> UnitOwnershipResponse:
    """Update ownership percentage or primary status."""
    service = OwnershipService(db)
    return await service.update_ownership(society_id, ownership_id, data, current_user.id)


@router.post("/ownerships/{ownership_id}/end", response_model=UnitOwnershipResponse)
async def end_unit_ownership(
    ownership_id: UUID,
    data: UnitOwnershipEndRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("units.manage")),
) -> UnitOwnershipResponse:
    """End or transfer ownership while preserving historical records."""
    service = OwnershipService(db)
    return await service.end_ownership(society_id, ownership_id, data, current_user.id)


@router.post("/ownerships/{ownership_id}/transfer", response_model=UnitOwnershipTransferResponse)
async def transfer_unit_ownership(
    ownership_id: UUID,
    data: UnitOwnershipTransferRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("units.manage")),
) -> UnitOwnershipTransferResponse:
    """Transfer full or partial ownership to another user atomically."""
    service = OwnershipService(db)
    return await service.transfer_ownership(society_id, ownership_id, data, current_user.id)
