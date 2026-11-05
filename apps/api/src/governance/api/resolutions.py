"""Phase 18 Governance Resolution REST Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission
from apps.api.src.database.session import get_db_session
from apps.api.src.governance.enums import ResolutionStatus, VotingType
from apps.api.src.governance.exceptions import GovernanceError, GovernanceNotFoundError
from apps.api.src.governance.governance_service import GovernanceService
from apps.api.src.governance.schemas import (
    ResolutionCastVote,
    ResolutionCreate,
    ResolutionResponse,
    ResolutionStateTransition,
    ResolutionUpdate,
    ResolutionVoteResponse,
)

router = APIRouter(prefix="/governance/resolutions", tags=["Governance Resolutions"])


@router.post("", response_model=ResolutionResponse, status_code=status.HTTP_201_CREATED)
async def create_resolution(
    request: Request,
    data: ResolutionCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("resolution.create")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        resolution = await service.create_resolution(society_id, current_user.id, data)
        return resolution
    except GovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("", response_model=list[ResolutionResponse])
async def list_resolutions(
    request: Request,
    meeting_id: UUID | None = Query(None),
    committee_id: UUID | None = Query(None),
    resolution_status: ResolutionStatus | None = Query(None, alias="status"),
    voting_type: VotingType | None = Query(None, alias="type"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("resolution.view")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    resolutions = await service.list_resolutions(
        society_id=society_id,
        meeting_id=meeting_id,
        committee_id=committee_id,
        resolution_status=resolution_status,
        voting_type=voting_type,
        limit=limit,
        offset=offset,
    )
    return resolutions


@router.get("/{resolution_id}", response_model=ResolutionResponse)
async def get_resolution(
    request: Request,
    resolution_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("resolution.view")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        resolution = await service.get_resolution(society_id, resolution_id)
        return resolution
    except GovernanceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e


@router.patch("/{resolution_id}", response_model=ResolutionResponse)
async def update_resolution(
    request: Request,
    resolution_id: UUID,
    data: ResolutionUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("resolution.create")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        resolution = await service.update_resolution(society_id, resolution_id, data)
        return resolution
    except GovernanceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except GovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.post("/{resolution_id}/transition", response_model=ResolutionResponse)
async def transition_resolution_status(
    request: Request,
    resolution_id: UUID,
    transition: ResolutionStateTransition,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("resolution.create")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        resolution = await service.transition_resolution_status(
            society_id, resolution_id, transition, current_user.id
        )
        return resolution
    except GovernanceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except GovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.post(
    "/{resolution_id}/vote", response_model=ResolutionVoteResponse, status_code=status.HTTP_201_CREATED
)
async def cast_vote(
    request: Request,
    resolution_id: UUID,
    vote_data: ResolutionCastVote,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("resolution.vote")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        vote = await service.cast_vote(
            society_id, resolution_id, voter_id=current_user.id, vote_data=vote_data
        )
        return vote
    except GovernanceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except GovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("/{resolution_id}/votes", response_model=list[ResolutionVoteResponse])
async def list_votes(
    request: Request,
    resolution_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("resolution.view")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    votes = await service.list_votes(society_id, resolution_id)
    return votes
