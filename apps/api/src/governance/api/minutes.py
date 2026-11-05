"""Phase 18 Governance Meeting Minutes REST Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission
from apps.api.src.database.session import get_db_session
from apps.api.src.governance.exceptions import GovernanceError, GovernanceNotFoundError
from apps.api.src.governance.governance_service import GovernanceService
from apps.api.src.governance.schemas import MeetingMinutesCreate, MeetingMinutesResponse

router = APIRouter(prefix="/governance/meetings", tags=["Governance Minutes"])


@router.post(
    "/{meeting_id}/minutes", response_model=MeetingMinutesResponse, status_code=status.HTTP_201_CREATED
)
async def create_meeting_minutes(
    request: Request,
    meeting_id: UUID,
    data: MeetingMinutesCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("minutes.create")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        minutes = await service.create_meeting_minutes(
            society_id, meeting_id, prepared_by=current_user.id, data=data
        )
        return minutes
    except GovernanceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except GovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("/{meeting_id}/minutes", response_model=MeetingMinutesResponse)
async def get_meeting_minutes(
    request: Request,
    meeting_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("meeting.view")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        minutes = await service.get_meeting_minutes(society_id, meeting_id)
        if not minutes:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Minutes not found for meeting")
        return minutes
    except GovernanceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e


@router.post("/{meeting_id}/minutes/approve", response_model=MeetingMinutesResponse)
async def approve_and_publish_minutes(
    request: Request,
    meeting_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("minutes.approve")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        minutes = await service.approve_and_publish_minutes(
            society_id, meeting_id, approver_id=current_user.id
        )
        return minutes
    except GovernanceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except GovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e
