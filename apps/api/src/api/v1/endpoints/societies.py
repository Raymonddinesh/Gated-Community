"""Minimal Administrative Hierarchy Endpoints for Schema Validation."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission
from apps.api.src.auth.schemas import (
    CreateMembershipRequest,
    GenericActionResponse,
    MembershipResponse,
    RoleAssignmentRequest,
    RoleAssignmentResponse,
)
from apps.api.src.core.exceptions import (
    AuthorizationException,
    NotFoundException,
    TenantContextMismatchException,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.repositories.audit_repository import AuditRepository
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.repositories.membership_repository import MembershipRepository
from apps.api.src.database.repositories.society_repository import SocietyRepository
from apps.api.src.database.repositories.user_repository import UserRepository
from apps.api.src.database.session import get_db_session

router = APIRouter(tags=["Societies & Spatial Hierarchy"])


# Response Schemas
class SocietyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    legal_name: str
    display_name: str
    city: str
    state: str
    country: str
    timezone: str
    status: str


class BlockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    code: str
    display_name: str
    sequence_order: int
    status: str


class FloorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    block_id: UUID
    floor_number: int
    display_name: str
    sequence_order: int
    status: str


class UnitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    society_id: UUID
    block_id: UUID
    floor_id: UUID
    unit_number: str
    unit_type: str
    carpet_area_sqft: float | None
    occupancy_status: str
    status: str


@router.get("/societies", response_model=list[SocietyResponse])
async def list_societies(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db_session),
) -> list[SocietyResponse]:
    """List registered societies (platform-level)."""
    repo = SocietyRepository(session)
    societies = await repo.list_societies(limit=limit, offset=offset)
    return [SocietyResponse.model_validate(s) for s in societies]


@router.get("/societies/{society_id}", response_model=SocietyResponse)
async def get_society(
    society_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> SocietyResponse:
    """Retrieve details for a specific society."""
    repo = SocietyRepository(session)
    society = await repo.get_society_by_id(society_id)
    if not society:
        raise NotFoundException(f"Society with ID '{society_id}' not found.")
    return SocietyResponse.model_validate(society)


@router.get("/societies/{society_id}/blocks", response_model=list[BlockResponse])
async def list_society_blocks(
    society_id: UUID,
    x_society_id: UUID | None = Header(None, alias="X-Society-ID"),
    session: AsyncSession = Depends(get_db_session),
) -> list[BlockResponse]:
    """List physical blocks/wings in a society."""
    if x_society_id is not None and x_society_id != society_id:
        raise TenantContextMismatchException(
            message=f"Tenant mismatch: URL specifies society '{society_id}' but X-Society-ID header specifies '{x_society_id}'."
        )
    repo = SocietyRepository(session)
    society = await repo.get_society_by_id(society_id)
    if not society:
        raise NotFoundException(f"Society with ID '{society_id}' not found.")
    blocks = await repo.get_blocks_for_society(society_id)
    return [BlockResponse.model_validate(b) for b in blocks]


@router.get("/blocks/{block_id}/floors", response_model=list[FloorResponse])
async def list_block_floors(
    block_id: UUID,
    x_society_id: UUID | None = Header(None, alias="X-Society-ID"),
    session: AsyncSession = Depends(get_db_session),
) -> list[FloorResponse]:
    """List floors within a block, optionally scoped by society hint."""
    repo = SocietyRepository(session)
    block = await repo.get_block_by_id(block_id, society_id=x_society_id)
    if not block:
        raise NotFoundException(f"Block with ID '{block_id}' not found.")
    floors = await repo.get_floors_for_block(block_id, society_id=x_society_id)
    return [FloorResponse.model_validate(f) for f in floors]


@router.get("/floors/{floor_id}/units", response_model=list[UnitResponse])
async def list_floor_units(
    floor_id: UUID,
    x_society_id: UUID | None = Header(None, alias="X-Society-ID"),
    session: AsyncSession = Depends(get_db_session),
) -> list[UnitResponse]:
    """List units on a floor, optionally scoped by society hint."""
    repo = SocietyRepository(session)
    floor = await repo.get_floor_by_id(floor_id, society_id=x_society_id)
    if not floor:
        raise NotFoundException(f"Floor with ID '{floor_id}' not found.")
    units = await repo.get_units_for_floor(floor_id, society_id=x_society_id)
    return [UnitResponse.model_validate(u) for u in units]


# --- Phase 3 RBAC & Tenant Membership Administration Endpoints ---


@router.post(
    "/societies/{society_id}/memberships",
    response_model=MembershipResponse,
)
async def create_society_membership(
    society_id: UUID,
    payload: CreateMembershipRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    _authorized_user: User = Depends(require_permission("user.manage")),
    session: AsyncSession = Depends(get_db_session),
) -> MembershipResponse:
    """
    Add a registered user to a society tenant.
    Enforces tenant context validation and requires user.manage capability.
    """
    user_repo = UserRepository(session)
    target_user = await user_repo.get_by_id(payload.user_id)
    if not target_user:
        raise NotFoundException(f"Target user '{payload.user_id}' does not exist.")

    membership_repo = MembershipRepository(session)
    membership = await membership_repo.create_membership(
        user_id=payload.user_id,
        society_id=society_id,
        status=payload.membership_status,
    )

    audit_repo = AuditRepository(session)
    await audit_repo.log_event(
        action="MEMBERSHIP_CREATED",
        entity_type="membership",
        entity_id=str(membership.id),
        society_id=society_id,
        actor_user_id=current_user.id,
        correlation_id=getattr(request.state, "correlation_id", None),
        after_state={"user_id": str(payload.user_id), "status": payload.membership_status},
    )

    return MembershipResponse(
        id=membership.id,
        user_id=membership.user_id,
        society_id=membership.society_id,
        membership_status=membership.membership_status,
    )


@router.post(
    "/societies/{society_id}/roles/assign",
    response_model=RoleAssignmentResponse,
)
async def assign_society_role(
    society_id: UUID,
    payload: RoleAssignmentRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    _authorized_user: User = Depends(require_permission("role.assign")),
    session: AsyncSession = Depends(get_db_session),
) -> RoleAssignmentResponse:
    """
    Assign a tenant-scoped role to a member.
    Enforces privilege-escalation controls:
    - Non-SUPER_ADMIN users cannot assign PLATFORM roles or SUPER_ADMIN.
    - Target user must hold an active membership in the target society.
    """
    authz_repo = AuthorizationRepository(session)
    caller_roles = await authz_repo.get_user_roles(current_user.id, society_id)
    caller_role_codes = {r.code for r in caller_roles}

    # Privilege Escalation Guard: Only SUPER_ADMIN can assign SUPER_ADMIN
    if payload.role_code == "SUPER_ADMIN" and "SUPER_ADMIN" not in caller_role_codes:
        raise AuthorizationException(
            "Privilege escalation prevented: Only platform SUPER_ADMIN can assign SUPER_ADMIN role."
        )

    # Verify target user has membership
    membership_repo = MembershipRepository(session)
    is_member = await membership_repo.verify_user_society_membership(payload.user_id, society_id)
    if not is_member:
        raise AuthorizationException(
            "Target user must be an active member of this society before receiving roles."
        )

    target_role = await authz_repo.get_role_by_code(payload.role_code, scope_type="SOCIETY")
    if not target_role:
        # Check platform role if caller is SUPER_ADMIN
        if "SUPER_ADMIN" in caller_role_codes:
            target_role = await authz_repo.get_role_by_code(payload.role_code, scope_type="PLATFORM")
        if not target_role:
            raise NotFoundException(f"Role with code '{payload.role_code}' not found.")

    assignment = await authz_repo.assign_role(
        user_id=payload.user_id,
        role_id=target_role.id,
        society_id=society_id if target_role.scope_type == "SOCIETY" else None,
        scope_type=target_role.scope_type,
    )

    audit_repo = AuditRepository(session)
    await audit_repo.log_event(
        action="ROLE_ASSIGNED",
        entity_type="role_assignment",
        entity_id=str(assignment.id),
        society_id=society_id,
        actor_user_id=current_user.id,
        correlation_id=getattr(request.state, "correlation_id", None),
        after_state={"user_id": str(payload.user_id), "role_code": payload.role_code},
    )

    return RoleAssignmentResponse(
        id=assignment.id,
        user_id=assignment.user_id,
        role_code=target_role.code,
        society_id=assignment.society_id,
        status=assignment.status,
    )


@router.post(
    "/societies/{society_id}/roles/revoke",
    response_model=GenericActionResponse,
)
async def revoke_society_role(
    society_id: UUID,
    payload: RoleAssignmentRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    _authorized_user: User = Depends(require_permission("role.assign")),
    session: AsyncSession = Depends(get_db_session),
) -> GenericActionResponse:
    """Revoke a role assignment within a society."""
    authz_repo = AuthorizationRepository(session)
    target_role = await authz_repo.get_role_by_code(payload.role_code, scope_type="SOCIETY")
    if not target_role:
        target_role = await authz_repo.get_role_by_code(payload.role_code, scope_type="PLATFORM")
        if not target_role:
            raise NotFoundException(f"Role with code '{payload.role_code}' not found.")

    await authz_repo.revoke_role(
        user_id=payload.user_id,
        role_id=target_role.id,
        society_id=society_id,
    )

    audit_repo = AuditRepository(session)
    await audit_repo.log_event(
        action="ROLE_REVOKED",
        entity_type="role_assignment",
        entity_id=f"{payload.user_id}:{payload.role_code}",
        society_id=society_id,
        actor_user_id=current_user.id,
        correlation_id=getattr(request.state, "correlation_id", None),
        after_state={"user_id": str(payload.user_id), "role_code": payload.role_code},
    )

    return GenericActionResponse(message=f"Role '{payload.role_code}' revoked successfully.")
