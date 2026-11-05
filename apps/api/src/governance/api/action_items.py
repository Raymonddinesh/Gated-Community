"""Phase 18 Governance Action Item REST Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission
from apps.api.src.database.session import get_db_session
from apps.api.src.governance.enums import ActionItemStatus
from apps.api.src.governance.exceptions import GovernanceError, GovernanceNotFoundError
from apps.api.src.governance.governance_service import GovernanceService
from apps.api.src.governance.schemas import (
    MeetingActionItemCreate,
    MeetingActionItemResponse,
    MeetingActionItemUpdate,
)

router = APIRouter(prefix="/governance/action-items", tags=["Governance Action Items"])


@router.post("", response_model=MeetingActionItemResponse, status_code=status.HTTP_201_CREATED)
async def create_action_item(
    request: Request,
    data: MeetingActionItemCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("action_item.manage")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        action_item = await service.create_action_item(society_id, data)
        return action_item
    except GovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("", response_model=list[MeetingActionItemResponse])
async def list_action_items(
    request: Request,
    meeting_id: UUID | None = Query(None),
    assignee_id: UUID | None = Query(None),
    item_status: ActionItemStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("meeting.view")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    action_items = await service.list_action_items(
        society_id=society_id,
        meeting_id=meeting_id,
        assignee_id=assignee_id,
        item_status=item_status,
        limit=limit,
        offset=offset,
    )
    return action_items


@router.patch("/{action_item_id}", response_model=MeetingActionItemResponse)
async def update_action_item(
    request: Request,
    action_item_id: UUID,
    data: MeetingActionItemUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("action_item.manage")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        action_item = await service.update_action_item(society_id, action_item_id, data)
        return action_item
    except GovernanceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except GovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e
