"""Resident Profiles and Self-Service API Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import (
    get_current_user,
    require_permission,
    resolve_society_context,
)
from apps.api.src.core.exceptions import AuthorizationException
from apps.api.src.database.models.identity import User
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.session import get_db_session
from apps.api.src.residents.application.household_service import HouseholdService
from apps.api.src.residents.application.resident_service import ResidentService
from apps.api.src.residents.schemas import (
    EmergencyContactUpdate,
    MyHomeResponse,
    ResidentCreateRequest,
    ResidentProfileUpdate,
    ResidentResponse,
)

router = APIRouter(tags=["Residents"])


# ---------------------------------------------------------------------------
# Self-Service Endpoints (/residents/me)
# ---------------------------------------------------------------------------
@router.get("/residents/me", response_model=ResidentResponse)
async def get_my_resident_profile(
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
) -> ResidentResponse:
    """Retrieve the authenticated resident's localized profile preferences and completeness."""
    service = ResidentService(db)
    return await service.get_my_profile(current_user.id, society_id)


@router.patch("/residents/me", response_model=ResidentResponse)
async def update_my_resident_profile(
    data: ResidentProfileUpdate,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
) -> ResidentResponse:
    """Update personal localized profile preferences, emergency contacts, or language."""
    service = ResidentService(db)
    return await service.update_my_profile(current_user.id, society_id, data)


@router.patch("/residents/me/emergency", response_model=ResidentResponse)
async def update_my_emergency_contact(
    data: EmergencyContactUpdate,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
) -> ResidentResponse:
    """Self-service emergency contact update."""
    service = ResidentService(db)
    return await service.update_my_emergency_contact(current_user.id, society_id, data)


@router.get("/residents/me/home", response_model=MyHomeResponse)
async def get_my_home(
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
) -> MyHomeResponse:
    """Retrieve aggregated household view: unit details, occupants, family, and delegates."""
    service = HouseholdService(db)
    return await service.get_my_home(current_user.id, society_id)


@router.get("/residents/me/vehicles")
async def get_my_resident_vehicles(
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
):
    """Retrieve all vehicles associated with the authenticated resident."""
    from apps.api.src.vehicles.application.vehicle_service import VehicleService
    from apps.api.src.vehicles.schemas import VehicleResponse

    service = VehicleService(db)
    vehicles = await service.get_my_vehicles(society_id, current_user.id)
    return [VehicleResponse.model_validate(v) for v in vehicles]


# ---------------------------------------------------------------------------
# Administrative & Directory Endpoints
# ---------------------------------------------------------------------------
@router.get("/residents", response_model=list[ResidentResponse])
async def search_residents(
    query: str | None = Query(None, description="Search by name, phone, or email"),
    unit_number: str | None = Query(None, description="Filter by unit number"),
    block_code: str | None = Query(None, description="Filter by block code"),
    status: str | None = Query(None, description="Filter by resident status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
) -> list[ResidentResponse]:
    """Search society residents with tenant-level DB boundary and privacy masking."""
    authz = AuthorizationRepository(db)
    roles = [r.code for r in await authz.get_user_roles(current_user.id, society_id)]
    perms = await authz.get_user_permission_codes(current_user.id, society_id)

    # Basic directory read check
    if not (
        any(r in ("SUPER_ADMIN", "SOCIETY_ADMIN", "SECRETARY", "TREASURER") for r in roles)
        or "society.read" in perms
    ):
        raise AuthorizationException("Forbidden: You lack permission to browse the society directory.")

    service = ResidentService(db)
    return await service.search_residents(
        society_id=society_id,
        query=query,
        unit_number=unit_number,
        block_code=block_code,
        status=status,
        limit=limit,
        offset=offset,
        requester_user_id=current_user.id,
        permissions=perms,
        roles=roles,
    )


@router.post("/residents", response_model=ResidentResponse)
async def create_resident(
    data: ResidentCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("resident.create")),
) -> ResidentResponse:
    """Create a resident profile association for an existing user."""
    service = ResidentService(db)
    return await service.create_resident(society_id, data, current_user.id)


@router.get("/residents/{profile_id}", response_model=ResidentResponse)
async def get_resident_details(
    profile_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
) -> ResidentResponse:
    """Retrieve resident details with privacy masking."""
    authz = AuthorizationRepository(db)
    roles = [r.code for r in await authz.get_user_roles(current_user.id, society_id)]
    perms = await authz.get_user_permission_codes(current_user.id, society_id)

    service = ResidentService(db)
    return await service.get_resident(
        profile_id=profile_id,
        society_id=society_id,
        requester_user_id=current_user.id,
        permissions=perms,
        roles=roles,
    )


@router.patch("/residents/{profile_id}", response_model=ResidentResponse)
async def update_resident_details(
    profile_id: UUID,
    data: ResidentProfileUpdate,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("resident.update")),
) -> ResidentResponse:
    """Administrative update of a resident's profile."""
    service = ResidentService(db)
    return await service.update_resident(profile_id, society_id, data, current_user.id)
