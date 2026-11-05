"""API Router for Staff Profiles."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, resolve_society_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.session import get_db_session
from apps.api.src.staff.application.staff_service import StaffProfileService
from apps.api.src.staff.schemas import (
    StaffContactResponse,
    StaffProfileCreateRequest,
    StaffProfileDetailResponse,
    StaffProfileSummaryResponse,
    StaffStatusUpdateRequest,
)

router = APIRouter(prefix="/profiles", tags=["Staff Profiles"])


@router.post("", response_model=StaffProfileDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_staff(
    request: StaffProfileCreateRequest,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> StaffProfileDetailResponse:
    """Create a new staff profile in society."""
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "staff.create" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to create staff profiles.")

    service = StaffProfileService(db)
    staff = await service.create_staff_profile(request, society_id, current_user)
    contact = await service.repo.get_contact(staff.id, society_id)

    return StaffProfileDetailResponse(
        id=staff.id,
        society_id=staff.society_id,
        user_id=staff.user_id,
        staff_code=staff.staff_code,
        first_name=staff.first_name,
        middle_name=staff.middle_name,
        last_name=staff.last_name,
        display_name=staff.display_name,
        preferred_name=staff.preferred_name,
        profile_photo_url=staff.profile_photo_url,
        date_of_joining=staff.date_of_joining,
        engagement_type=staff.engagement_type,
        status=staff.status,
        primary_role_id=staff.primary_role_id,
        primary_role_name=staff.primary_role.name if staff.primary_role else None,
        notes=staff.notes,
        contact=StaffContactResponse.model_validate(contact) if contact else None,
        created_at=staff.created_at,
        updated_at=staff.updated_at,
    )


@router.get("", response_model=list[StaffProfileSummaryResponse])
async def list_staff(
    status_filter: str | None = Query(None, alias="status"),
    engagement_type: str | None = Query(None),
    role_id: uuid.UUID | None = Query(None),
    team_id: uuid.UUID | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[StaffProfileSummaryResponse]:
    """List staff profiles with operational summary metadata."""
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "staff.view" not in perms and "maintenance.view_all" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to view staff profiles.")

    service = StaffProfileService(db)
    staff_list = await service.list_staff(
        society_id=society_id,
        status=status_filter,
        engagement_type=engagement_type,
        role_id=role_id,
        team_id=team_id,
        search=search,
        offset=offset,
        limit=limit,
    )

    return [
        StaffProfileSummaryResponse(
            id=s.id,
            society_id=s.society_id,
            staff_code=s.staff_code,
            display_name=s.display_name,
            preferred_name=s.preferred_name,
            profile_photo_url=s.profile_photo_url,
            engagement_type=s.engagement_type,
            status=s.status,
            primary_role_id=s.primary_role_id,
            primary_role_name=s.primary_role.name if s.primary_role else None,
        )
        for s in staff_list
    ]


@router.get("/{staff_id}", response_model=StaffProfileDetailResponse)
async def get_staff_detail(
    staff_id: uuid.UUID,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> StaffProfileDetailResponse:
    """Get staff detail. Privacy-sensitive contact details included if staff.view_sensitive perm exists."""
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "staff.view" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to view staff details.")

    service = StaffProfileService(db)
    staff = await service.get_staff_profile(staff_id, society_id)

    contact_resp = None
    if "staff.view_sensitive" in perms:
        contact = await service.repo.get_contact(staff.id, society_id)
        if contact:
            contact_resp = StaffContactResponse.model_validate(contact)

    return StaffProfileDetailResponse(
        id=staff.id,
        society_id=staff.society_id,
        user_id=staff.user_id,
        staff_code=staff.staff_code,
        first_name=staff.first_name,
        middle_name=staff.middle_name,
        last_name=staff.last_name,
        display_name=staff.display_name,
        preferred_name=staff.preferred_name,
        profile_photo_url=staff.profile_photo_url,
        date_of_joining=staff.date_of_joining,
        engagement_type=staff.engagement_type,
        status=staff.status,
        primary_role_id=staff.primary_role_id,
        primary_role_name=staff.primary_role.name if staff.primary_role else None,
        notes=staff.notes if "staff.view_sensitive" in perms else None,
        contact=contact_resp,
        created_at=staff.created_at,
        updated_at=staff.updated_at,
    )


@router.patch("/{staff_id}/status", response_model=StaffProfileDetailResponse)
async def transition_status(
    staff_id: uuid.UUID,
    request: StaffStatusUpdateRequest,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> StaffProfileDetailResponse:
    """Transition staff status lifecycle (e.g. ONBOARDING -> ACTIVE, ACTIVE -> SUSPENDED)."""
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "staff.status.manage" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to manage staff status.")

    service = StaffProfileService(db)
    staff = await service.transition_staff_status(staff_id, society_id, request, current_user)
    contact = await service.repo.get_contact(staff.id, society_id)

    return StaffProfileDetailResponse(
        id=staff.id,
        society_id=staff.society_id,
        user_id=staff.user_id,
        staff_code=staff.staff_code,
        first_name=staff.first_name,
        middle_name=staff.middle_name,
        last_name=staff.last_name,
        display_name=staff.display_name,
        preferred_name=staff.preferred_name,
        profile_photo_url=staff.profile_photo_url,
        date_of_joining=staff.date_of_joining,
        engagement_type=staff.engagement_type,
        status=staff.status,
        primary_role_id=staff.primary_role_id,
        primary_role_name=staff.primary_role.name if staff.primary_role else None,
        notes=staff.notes,
        contact=StaffContactResponse.model_validate(contact) if contact else None,
        created_at=staff.created_at,
        updated_at=staff.updated_at,
    )
