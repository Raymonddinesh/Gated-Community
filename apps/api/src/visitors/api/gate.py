"""API Endpoints for Gate Operations, Walk-in Check-in, Entry, Exit, and Emergency Overrides."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import (
    require_permission,
    resolve_society_context,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.visitors.application.access_service import VisitorAccessService
from apps.api.src.visitors.application.visitor_service import VisitorService
from apps.api.src.visitors.schemas import (
    EmergencyOverrideEntryRequest,
    VisitorAccessRecordResponse,
    VisitorApprovalResponse,
    VisitorGateEntryRequest,
    VisitorGateExitRequest,
    VisitorResponse,
    WalkInVisitorEntryRequest,
)

router = APIRouter(tags=["Visitor Gate Operations"])


@router.post("/visitors/walkin", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register_walkin_visitor(
    data: WalkInVisitorEntryRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("visitor.entry")),
) -> dict:
    """Security guard registers walk-in visitor and initiates resident approval request."""
    service = VisitorService(db)
    visitor, approval = await service.record_walkin_request(society_id, current_user.id, data)
    return {
        "visitor": VisitorResponse.model_validate(visitor),
        "approval": VisitorApprovalResponse.model_validate(approval),
    }


@router.post(
    "/visitors/entry", response_model=VisitorAccessRecordResponse, status_code=status.HTTP_201_CREATED
)
async def record_visitor_entry(
    data: VisitorGateEntryRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("visitor.entry")),
) -> VisitorAccessRecordResponse:
    """Security guard checks in an approved or pre-approved visitor at the gate."""
    service = VisitorAccessService(db)
    record = await service.record_entry(society_id, current_user.id, data)
    return VisitorAccessRecordResponse.model_validate(record)


@router.post("/visitors/exit/{record_id}", response_model=VisitorAccessRecordResponse)
async def record_visitor_exit(
    record_id: UUID,
    data: VisitorGateExitRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("visitor.exit")),
) -> VisitorAccessRecordResponse:
    """Security guard checks out a visitor at the gate."""
    service = VisitorAccessService(db)
    record = await service.record_exit(society_id, record_id, current_user.id, data)
    return VisitorAccessRecordResponse.model_validate(record)


@router.post(
    "/visitors/emergency-override",
    response_model=VisitorAccessRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_emergency_override_entry(
    data: EmergencyOverrideEntryRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("visitor.emergency.override")),
) -> VisitorAccessRecordResponse:
    """Authorized security administrator executes audit-logged emergency entry override."""
    service = VisitorAccessService(db)
    record = await service.record_emergency_override_entry(society_id, current_user.id, data)
    return VisitorAccessRecordResponse.model_validate(record)
