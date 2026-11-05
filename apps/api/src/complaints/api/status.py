"""API Router for Complaint Status Transitions & Resolution."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import (
    require_permission,
    resolve_society_context,
)
from apps.api.src.complaints.application.status_service import ComplaintStatusService
from apps.api.src.complaints.schemas import (
    ComplaintResolutionCreateRequest,
    ComplaintResponse,
    ComplaintStatusHistoryResponse,
    ComplaintStatusUpdateRequest,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session

router = APIRouter(tags=["Complaint Status Operations"])


@router.post(
    "/complaints/{complaint_id}/status",
    response_model=ComplaintResponse,
)
async def update_complaint_status(
    complaint_id: UUID,
    data: ComplaintStatusUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("complaint.status.manage")),
) -> ComplaintResponse:
    """Transition complaint status with state machine validation."""
    service = ComplaintStatusService(db)
    complaint = await service.transition_status(
        society_id=society_id,
        complaint_id=complaint_id,
        actor_user_id=current_user.id,
        target_status=data.status.value,
        reason=data.reason,
    )
    return ComplaintResponse.model_validate(complaint)


@router.post(
    "/complaints/{complaint_id}/resolve",
    response_model=ComplaintResponse,
)
async def resolve_complaint(
    complaint_id: UUID,
    data: ComplaintResolutionCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("complaint.resolve")),
) -> ComplaintResponse:
    """Resolve a complaint with resolution summary."""
    service = ComplaintStatusService(db)
    complaint = await service.transition_status(
        society_id=society_id,
        complaint_id=complaint_id,
        actor_user_id=current_user.id,
        target_status="RESOLVED",
        resolution_data=data,
    )
    return ComplaintResponse.model_validate(complaint)


@router.post(
    "/complaints/{complaint_id}/reopen",
    response_model=ComplaintResponse,
)
async def reopen_complaint(
    complaint_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("complaint.reopen")),
) -> ComplaintResponse:
    """Reopen a resolved/closed complaint."""
    service = ComplaintStatusService(db)
    complaint = await service.transition_status(
        society_id=society_id,
        complaint_id=complaint_id,
        actor_user_id=current_user.id,
        target_status="REOPENED",
        reason="Reopened by user/resident",
    )
    return ComplaintResponse.model_validate(complaint)


@router.get(
    "/complaints/{complaint_id}/history",
    response_model=list[ComplaintStatusHistoryResponse],
)
async def get_complaint_history(
    complaint_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("complaint.create")),
) -> list[ComplaintStatusHistoryResponse]:
    """Fetch status audit history for a complaint."""
    service = ComplaintStatusService(db)
    history = await service.get_history(society_id, complaint_id)
    return [ComplaintStatusHistoryResponse.model_validate(h) for h in history]
