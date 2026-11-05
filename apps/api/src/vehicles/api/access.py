"""API endpoints for Vehicle Access Control and Gate Logs."""

import math
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import (
    require_permission,
    resolve_society_context,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.vehicles.application.access_service import VehicleAccessService
from apps.api.src.vehicles.schemas import (
    VehicleAccessRecordCreateRequest,
    VehicleAccessRecordResponse,
)

router = APIRouter(tags=["Vehicle Access"])


class AccessRecordListResponse(BaseModel):
    items: list[VehicleAccessRecordResponse]
    total: int
    page: int
    size: int

    pages: int


@router.get("/vehicles/access/records", response_model=AccessRecordListResponse)
async def list_vehicle_access_records(
    query: str | None = Query(None, description="Search plate snapshot or gate identifier"),
    vehicle_id: UUID | None = Query(None, description="Filter by vehicle ID"),
    access_type: str | None = Query(None, description="Filter ENTRY or EXIT"),
    gate_identifier: str | None = Query(None, description="Filter by gate identifier"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(50, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("vehicle.access.view")),
) -> AccessRecordListResponse:
    """Retrieve immutable vehicle access audit logs."""
    service = VehicleAccessService(db)
    items, total = await service.search_records(
        society_id=society_id,
        query=query,
        vehicle_id=vehicle_id,
        access_type=access_type,
        gate_identifier=gate_identifier,
        page=page,
        size=size,
    )
    pages = math.ceil(total / size) if size > 0 else 0
    return AccessRecordListResponse(
        items=[VehicleAccessRecordResponse.model_validate(r) for r in items],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.post(
    "/vehicles/access/records",
    response_model=VehicleAccessRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_vehicle_access(
    data: VehicleAccessRecordCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("vehicle.access.record")),
) -> VehicleAccessRecordResponse:
    """Record a gate entry/exit event via Manual, RFID, or ANPR hardware abstraction."""
    service = VehicleAccessService(db)
    record = await service.record_access(society_id, current_user.id, data)
    return VehicleAccessRecordResponse.model_validate(record)
