"""Vehicle management API endpoints."""

import math
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import (
    require_permission,
    resolve_society_context,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.vehicles.application.vehicle_service import VehicleService
from apps.api.src.vehicles.schemas import (
    VehicleCreateRequest,
    VehicleListResponse,
    VehicleResponse,
    VehicleStatusUpdateRequest,
    VehicleUpdateRequest,
    VehicleVerifyRequest,
)

router = APIRouter(tags=["Vehicles"])


@router.get("/vehicles/me", response_model=list[VehicleResponse])
async def get_my_vehicles(
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("vehicle.view")),
) -> list[VehicleResponse]:
    """Retrieve vehicles associated with the authenticated resident user."""
    service = VehicleService(db)
    vehicles = await service.get_my_vehicles(society_id, current_user.id)
    return [VehicleResponse.model_validate(v) for v in vehicles]


@router.get("/vehicles", response_model=VehicleListResponse)
async def search_vehicles(
    query: str | None = Query(None, description="Search plate, make, model"),
    vehicle_type: str | None = Query(None, description="Filter by vehicle type"),
    fuel_type: str | None = Query(None, description="Filter by fuel type"),
    is_ev: bool | None = Query(None, description="Filter by EV flag"),
    status: str | None = Query(None, description="Filter by lifecycle status"),
    verification_status: str | None = Query(None, description="Filter by verification status"),
    unit_id: UUID | None = Query(None, description="Filter by associated unit ID"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(50, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("vehicle.view")),
) -> VehicleListResponse:
    """Search and filter vehicles in the society."""
    service = VehicleService(db)
    items, total = await service.search(
        society_id=society_id,
        query=query,
        vehicle_type=vehicle_type,
        fuel_type=fuel_type,
        is_ev=is_ev,
        status=status,
        verification_status=verification_status,
        unit_id=unit_id,
        page=page,
        size=size,
    )
    pages = math.ceil(total / size) if size > 0 else 0
    return VehicleListResponse(
        items=[VehicleResponse.model_validate(v) for v in items],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.post("/vehicles", response_model=VehicleResponse, status_code=201)
async def register_vehicle(
    data: VehicleCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("vehicle.create")),
) -> VehicleResponse:
    """Register a new vehicle with deterministic registration number normalization."""
    service = VehicleService(db)
    vehicle = await service.register_vehicle(society_id, current_user.id, data)
    return VehicleResponse.model_validate(vehicle)


@router.get("/vehicles/{vehicle_id}", response_model=VehicleResponse)
async def get_vehicle(
    vehicle_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("vehicle.view")),
) -> VehicleResponse:
    """Get vehicle details by ID."""
    service = VehicleService(db)
    vehicle = await service.get_vehicle(society_id, vehicle_id)
    return VehicleResponse.model_validate(vehicle)


@router.patch("/vehicles/{vehicle_id}", response_model=VehicleResponse)
async def update_vehicle(
    vehicle_id: UUID,
    data: VehicleUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("vehicle.update")),
) -> VehicleResponse:
    """Update vehicle specifications and attributes."""
    service = VehicleService(db)
    vehicle = await service.update_vehicle(society_id, vehicle_id, current_user.id, data)
    return VehicleResponse.model_validate(vehicle)


@router.patch("/vehicles/{vehicle_id}/status", response_model=VehicleResponse)
async def update_vehicle_status(
    vehicle_id: UUID,
    data: VehicleStatusUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("vehicle.deactivate")),
) -> VehicleResponse:
    """Update vehicle lifecycle status (e.g. INACTIVE, SOLD, SCRAPPED)."""
    service = VehicleService(db)
    vehicle = await service.update_status(society_id, vehicle_id, current_user.id, data.status, data.notes)
    return VehicleResponse.model_validate(vehicle)


@router.post("/vehicles/{vehicle_id}/verify", response_model=VehicleResponse)
async def verify_vehicle(
    vehicle_id: UUID,
    data: VehicleVerifyRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("vehicle.verify")),
) -> VehicleResponse:
    """Audit-logged verification approval or rejection of a vehicle."""
    service = VehicleService(db)
    vehicle = await service.verify_vehicle(society_id, vehicle_id, current_user.id, data)
    return VehicleResponse.model_validate(vehicle)
