"""Household, Family Members, and Scoped Delegates API Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import (
    get_current_user,
    resolve_society_context,
)
from apps.api.src.core.exceptions import AuthorizationException
from apps.api.src.database.models.identity import User
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.session import get_db_session
from apps.api.src.residents.application.household_service import HouseholdService
from apps.api.src.residents.application.resident_service import ResidentService
from apps.api.src.residents.schemas import (
    DelegateCreate,
    DelegateResponse,
    DelegateRevokeRequest,
    FamilyMemberCreate,
    FamilyMemberResponse,
    FamilyMemberUpdate,
)

router = APIRouter(tags=["Household & Delegates"])


# ---------------------------------------------------------------------------
# Self-Service Household Endpoints
# ---------------------------------------------------------------------------
@router.get("/residents/me/family", response_model=list[FamilyMemberResponse])
async def list_my_family_members(
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
) -> list[FamilyMemberResponse]:
    """List family members for authenticated resident's household."""
    service = HouseholdService(db)
    occs = await service.occupancy_repo.get_occupancies_for_user(
        current_user.id, society_id, active_only=True
    )
    owns = await service.ownership_repo.get_ownerships_for_user(current_user.id, society_id, active_only=True)
    unit_id = occs[0].unit_id if occs else (owns[0].unit_id if owns else None)
    if not unit_id:
        return []
    return await service.list_family_members(society_id, unit_id, primary_resident_user_id=current_user.id)


@router.post("/residents/me/family", response_model=FamilyMemberResponse)
async def add_my_family_member(
    data: FamilyMemberCreate,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
) -> FamilyMemberResponse:
    """Add a family member to the authenticated resident's household."""
    service = HouseholdService(db)
    occs = await service.occupancy_repo.get_occupancies_for_user(
        current_user.id, society_id, active_only=True
    )
    owns = await service.ownership_repo.get_ownerships_for_user(current_user.id, society_id, active_only=True)
    unit_id = occs[0].unit_id if occs else (owns[0].unit_id if owns else None)
    if not unit_id:
        raise AuthorizationException("You do not have an active unit association in this society.")
    return await service.add_family_member(
        society_id=society_id,
        unit_id=unit_id,
        primary_resident_user_id=current_user.id,
        data=data,
        actor_user_id=current_user.id,
    )


@router.get("/residents/me/delegates", response_model=list[DelegateResponse])
async def list_my_delegates(
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
) -> list[DelegateResponse]:
    """List delegates granted by authenticated resident."""
    service = HouseholdService(db)
    return await service.list_delegates(
        society_id=society_id, delegator_user_id=current_user.id, active_only=False
    )


@router.post("/residents/me/delegates", response_model=DelegateResponse)
async def grant_my_delegate(
    data: DelegateCreate,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
) -> DelegateResponse:
    """Grant scoped delegation to another user for authenticated resident's unit."""
    service = HouseholdService(db)
    return await service.create_delegate(
        society_id=society_id,
        unit_id=data.unit_id,
        delegator_user_id=current_user.id,
        data=data,
        actor_user_id=current_user.id,
    )


# ---------------------------------------------------------------------------
# Admin & Entity-Scoped Household Endpoints
# ---------------------------------------------------------------------------
@router.get("/residents/{profile_id}/family", response_model=list[FamilyMemberResponse])
async def list_resident_family(
    profile_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
) -> list[FamilyMemberResponse]:
    """List family members for a resident profile."""
    res_service = ResidentService(db)
    profile = await res_service.resident_repo.get_profile_by_id(profile_id, society_id)
    if not profile:
        from apps.api.src.residents.domain.exceptions import ResidentNotFoundError

        raise ResidentNotFoundError()

    # Verify access: self or admin
    authz = AuthorizationRepository(db)
    roles = [r.code for r in await authz.get_user_roles(current_user.id, society_id)]
    is_admin = any(r in ("SUPER_ADMIN", "SOCIETY_ADMIN", "SECRETARY", "TREASURER") for r in roles)
    if not (is_admin or current_user.id == profile.user_id):
        raise AuthorizationException("Access forbidden to household records.")

    service = HouseholdService(db)
    occs = await service.occupancy_repo.get_occupancies_for_user(
        profile.user_id, society_id, active_only=True
    )
    owns = await service.ownership_repo.get_ownerships_for_user(profile.user_id, society_id, active_only=True)
    unit_id = occs[0].unit_id if occs else (owns[0].unit_id if owns else None)
    if not unit_id:
        return []
    return await service.list_family_members(society_id, unit_id, primary_resident_user_id=profile.user_id)


@router.post("/residents/{profile_id}/family", response_model=FamilyMemberResponse)
async def add_resident_family(
    profile_id: UUID,
    data: FamilyMemberCreate,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
) -> FamilyMemberResponse:
    """Add a family member to a resident's household."""
    res_service = ResidentService(db)
    profile = await res_service.resident_repo.get_profile_by_id(profile_id, society_id)
    if not profile:
        from apps.api.src.residents.domain.exceptions import ResidentNotFoundError

        raise ResidentNotFoundError()

    authz = AuthorizationRepository(db)
    roles = [r.code for r in await authz.get_user_roles(current_user.id, society_id)]
    is_admin = any(r in ("SUPER_ADMIN", "SOCIETY_ADMIN", "SECRETARY", "TREASURER") for r in roles)
    if not (is_admin or current_user.id == profile.user_id):
        raise AuthorizationException("Access forbidden.")

    service = HouseholdService(db)
    occs = await service.occupancy_repo.get_occupancies_for_user(
        profile.user_id, society_id, active_only=True
    )
    owns = await service.ownership_repo.get_ownerships_for_user(profile.user_id, society_id, active_only=True)
    unit_id = occs[0].unit_id if occs else (owns[0].unit_id if owns else None)
    if not unit_id:
        raise AuthorizationException("Resident has no active unit association.")

    return await service.add_family_member(
        society_id=society_id,
        unit_id=unit_id,
        primary_resident_user_id=profile.user_id,
        data=data,
        actor_user_id=current_user.id,
    )


@router.patch("/family/{member_id}", response_model=FamilyMemberResponse)
async def update_family_member(
    member_id: UUID,
    data: FamilyMemberUpdate,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
) -> FamilyMemberResponse:
    """Update family member details."""
    service = HouseholdService(db)
    member = await service.family_repo.get_family_member(member_id, society_id)
    if not member:
        from apps.api.src.residents.domain.exceptions import FamilyMemberNotFoundError

        raise FamilyMemberNotFoundError()

    authz = AuthorizationRepository(db)
    roles = [r.code for r in await authz.get_user_roles(current_user.id, society_id)]
    is_admin = any(r in ("SUPER_ADMIN", "SOCIETY_ADMIN", "SECRETARY", "TREASURER") for r in roles)
    if not (is_admin or current_user.id == member.primary_resident_user_id):
        raise AuthorizationException("Access forbidden.")

    return await service.update_family_member(society_id, member_id, data, current_user.id)


@router.delete("/family/{member_id}", response_model=FamilyMemberResponse)
async def remove_family_member(
    member_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
) -> FamilyMemberResponse:
    """Deactivate a family member."""
    service = HouseholdService(db)
    member = await service.family_repo.get_family_member(member_id, society_id)
    if not member:
        from apps.api.src.residents.domain.exceptions import FamilyMemberNotFoundError

        raise FamilyMemberNotFoundError()

    authz = AuthorizationRepository(db)
    roles = [r.code for r in await authz.get_user_roles(current_user.id, society_id)]
    is_admin = any(r in ("SUPER_ADMIN", "SOCIETY_ADMIN", "SECRETARY", "TREASURER") for r in roles)
    if not (is_admin or current_user.id == member.primary_resident_user_id):
        raise AuthorizationException("Access forbidden.")

    return await service.remove_family_member(society_id, member_id, current_user.id)


@router.get("/residents/{profile_id}/delegates", response_model=list[DelegateResponse])
async def list_resident_delegates(
    profile_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
) -> list[DelegateResponse]:
    """List delegates granted by a resident."""
    res_service = ResidentService(db)
    profile = await res_service.resident_repo.get_profile_by_id(profile_id, society_id)
    if not profile:
        from apps.api.src.residents.domain.exceptions import ResidentNotFoundError

        raise ResidentNotFoundError()

    authz = AuthorizationRepository(db)
    roles = [r.code for r in await authz.get_user_roles(current_user.id, society_id)]
    is_admin = any(r in ("SUPER_ADMIN", "SOCIETY_ADMIN", "SECRETARY", "TREASURER") for r in roles)
    if not (is_admin or current_user.id == profile.user_id):
        raise AuthorizationException("Access forbidden to delegation records.")

    service = HouseholdService(db)
    return await service.list_delegates(
        society_id=society_id, delegator_user_id=profile.user_id, active_only=False
    )


@router.post("/residents/{profile_id}/delegates", response_model=DelegateResponse)
async def grant_resident_delegate(
    profile_id: UUID,
    data: DelegateCreate,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
) -> DelegateResponse:
    """Grant delegation on behalf of or by a resident."""
    res_service = ResidentService(db)
    profile = await res_service.resident_repo.get_profile_by_id(profile_id, society_id)
    if not profile:
        from apps.api.src.residents.domain.exceptions import ResidentNotFoundError

        raise ResidentNotFoundError()

    authz = AuthorizationRepository(db)
    roles = [r.code for r in await authz.get_user_roles(current_user.id, society_id)]
    is_admin = any(r in ("SUPER_ADMIN", "SOCIETY_ADMIN", "SECRETARY", "TREASURER") for r in roles)
    if not (is_admin or current_user.id == profile.user_id):
        raise AuthorizationException("Access forbidden.")

    service = HouseholdService(db)
    return await service.create_delegate(
        society_id=society_id,
        unit_id=data.unit_id,
        delegator_user_id=profile.user_id,
        data=data,
        actor_user_id=current_user.id,
    )


@router.post("/delegates/{delegate_id}/revoke", response_model=DelegateResponse)
async def revoke_delegate(
    delegate_id: UUID,
    data: DelegateRevokeRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
) -> DelegateResponse:
    """Revoke a previously granted delegation."""
    service = HouseholdService(db)
    delegate = await service.delegate_repo.get_delegate(delegate_id, society_id)
    if not delegate:
        from apps.api.src.residents.domain.exceptions import DelegateNotFoundError

        raise DelegateNotFoundError()

    authz = AuthorizationRepository(db)
    roles = [r.code for r in await authz.get_user_roles(current_user.id, society_id)]
    is_admin = any(r in ("SUPER_ADMIN", "SOCIETY_ADMIN", "SECRETARY", "TREASURER") for r in roles)
    if not (is_admin or current_user.id == delegate.delegator_user_id):
        raise AuthorizationException("Access forbidden to revoke this delegation.")

    return await service.revoke_delegate(society_id, delegate_id, data, current_user.id)
