"""Phase 18 Governance Committee REST Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission
from apps.api.src.database.session import get_db_session
from apps.api.src.governance.enums import CommitteeType
from apps.api.src.governance.exceptions import GovernanceError, GovernanceNotFoundError
from apps.api.src.governance.governance_service import GovernanceService
from apps.api.src.governance.schemas import (
    CommitteeCreate,
    CommitteeMemberAdd,
    CommitteeMemberResponse,
    CommitteeResponse,
    CommitteeUpdate,
)

router = APIRouter(prefix="/governance/committees", tags=["Governance Committees"])


@router.post("", response_model=CommitteeResponse, status_code=status.HTTP_201_CREATED)
async def create_committee(
    request: Request,
    data: CommitteeCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("committee.manage")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        committee = await service.create_committee(society_id, data)
        return committee
    except GovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("", response_model=list[CommitteeResponse])
async def list_committees(
    request: Request,
    committee_type: CommitteeType | None = Query(None, alias="type"),
    is_active: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("committee.view")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    committees = await service.list_committees(
        society_id=society_id,
        committee_type=committee_type,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )
    return committees


@router.get("/{committee_id}", response_model=CommitteeResponse)
async def get_committee(
    request: Request,
    committee_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("committee.view")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        committee = await service.get_committee(society_id, committee_id)
        return committee
    except GovernanceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e


@router.patch("/{committee_id}", response_model=CommitteeResponse)
async def update_committee(
    request: Request,
    committee_id: UUID,
    data: CommitteeUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("committee.manage")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        committee = await service.update_committee(society_id, committee_id, data)
        return committee
    except GovernanceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except GovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.post(
    "/{committee_id}/members", response_model=CommitteeMemberResponse, status_code=status.HTTP_201_CREATED
)
async def add_committee_member(
    request: Request,
    committee_id: UUID,
    data: CommitteeMemberAdd,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("committee.manage")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        member = await service.add_committee_member(society_id, committee_id, data)
        return member
    except GovernanceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except GovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("/{committee_id}/members", response_model=list[CommitteeMemberResponse])
async def list_committee_members(
    request: Request,
    committee_id: UUID,
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("committee.view")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    members = await service.list_committee_members(society_id, committee_id, active_only=active_only)
    return members


@router.delete("/{committee_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_committee_member(
    request: Request,
    committee_id: UUID,
    member_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("committee.manage")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        await service.remove_committee_member(society_id, committee_id, member_id)
    except GovernanceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except GovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e
