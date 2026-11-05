"""API Router for Staff Teams."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, resolve_society_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.session import get_db_session
from apps.api.src.staff.application.team_service import StaffTeamService
from apps.api.src.staff.schemas import (
    StaffTeamCreateRequest,
    StaffTeamMembershipRequest,
    StaffTeamMembershipResponse,
    StaffTeamResponse,
)

router = APIRouter(prefix="/teams", tags=["Staff Teams"])


@router.post("", response_model=StaffTeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    request: StaffTeamCreateRequest,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> StaffTeamResponse:
    """Create a new staff team."""
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "staff.team.manage" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to manage staff teams.")

    service = StaffTeamService(db)
    team = await service.create_staff_team(request, society_id)
    return StaffTeamResponse.model_validate(team)


@router.get("", response_model=list[StaffTeamResponse])
async def list_teams(
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[StaffTeamResponse]:
    """List active staff teams."""
    service = StaffTeamService(db)
    teams = await service.list_staff_teams(society_id)
    return [StaffTeamResponse.model_validate(t) for t in teams]


@router.post("/memberships", response_model=StaffTeamMembershipResponse)
async def add_team_member(
    staff_id: uuid.UUID,
    request: StaffTeamMembershipRequest,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> StaffTeamMembershipResponse:
    """Add staff member to a team."""
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "staff.team.assign" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to assign staff to teams.")

    service = StaffTeamService(db)
    membership = await service.add_staff_to_team(
        staff_id=staff_id,
        team_id=request.team_id,
        society_id=society_id,
        is_primary=request.is_primary,
        assigned_by_user=current_user,
    )
    return StaffTeamMembershipResponse.model_validate(membership)
