"""API Router for Staff Roles."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, resolve_society_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.session import get_db_session
from apps.api.src.staff.application.role_service import StaffRoleService
from apps.api.src.staff.schemas import (
    StaffRoleAssignmentRequest,
    StaffRoleAssignmentResponse,
    StaffRoleCreateRequest,
    StaffRoleResponse,
)

router = APIRouter(prefix="/roles", tags=["Staff Roles"])


@router.post("", response_model=StaffRoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    request: StaffRoleCreateRequest,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> StaffRoleResponse:
    """Create a new operational staff role."""
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "staff.role.manage" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to manage staff roles.")

    service = StaffRoleService(db)
    role = await service.create_staff_role(request, society_id)
    return StaffRoleResponse.model_validate(role)


@router.get("", response_model=list[StaffRoleResponse])
async def list_roles(
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[StaffRoleResponse]:
    """List active operational staff roles."""
    service = StaffRoleService(db)
    roles = await service.list_staff_roles(society_id)
    return [StaffRoleResponse.model_validate(r) for r in roles]


@router.post("/assignments", response_model=StaffRoleAssignmentResponse)
async def assign_role(
    staff_id: uuid.UUID,
    request: StaffRoleAssignmentRequest,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> StaffRoleAssignmentResponse:
    """Assign an operational role to staff member."""
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "staff.role.manage" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to assign staff roles.")

    service = StaffRoleService(db)
    assignment = await service.assign_role_to_staff(
        staff_id=staff_id,
        role_id=request.role_id,
        society_id=society_id,
        is_primary=request.is_primary,
        assigned_by_user=current_user,
        reason=request.reason,
    )
    return StaffRoleAssignmentResponse.model_validate(assignment)
