"""API Router for Core Complaint Operations."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import (
    require_permission,
    resolve_society_context,
)
from apps.api.src.complaints.application.complaint_service import ComplaintService
from apps.api.src.complaints.domain.exceptions import ComplaintAccessDeniedError
from apps.api.src.complaints.schemas import (
    ComplaintCreateRequest,
    ComplaintPaginatedListResponse,
    ComplaintResponse,
    ComplaintUpdateRequest,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.session import get_db_session

router = APIRouter(tags=["Complaints Core Operations"])


@router.post(
    "/complaints",
    response_model=ComplaintResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_complaint(
    data: ComplaintCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("complaint.create")),
) -> ComplaintResponse:
    """Raise a new complaint or service request."""
    service = ComplaintService(db)
    complaint = await service.create_complaint(society_id, current_user.id, data)
    return ComplaintResponse.model_validate(complaint)


@router.get(
    "/complaints",
    response_model=ComplaintPaginatedListResponse,
)
async def search_complaints(
    query: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    priority: str | None = Query(None),
    category_id: UUID | None = Query(None),
    subcategory_id: UUID | None = Query(None),
    unit_id: UUID | None = Query(None),
    my_complaints_only: bool = Query(False),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("complaint.create")),
) -> ComplaintPaginatedListResponse:
    """Search and filter complaints with safe pagination and ownership checks."""
    authz_repo = AuthorizationRepository(db)
    roles = await authz_repo.get_user_roles(current_user.id, society_id)
    perms = await authz_repo.get_user_permission_codes(current_user.id, society_id)
    has_view_all = any(r.code == "SUPER_ADMIN" for r in roles) or "complaint.view_all" in perms

    raised_by_user_id = current_user.id if (my_complaints_only or not has_view_all) else None

    service = ComplaintService(db)
    items, total = await service.search_complaints(
        society_id=society_id,
        query=query,
        status=status_filter,
        priority=priority,
        category_id=category_id,
        subcategory_id=subcategory_id,
        unit_id=unit_id,
        raised_by_user_id=raised_by_user_id,
        page=page,
        size=size,
    )
    return ComplaintPaginatedListResponse(
        items=[ComplaintResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        size=size,
    )


@router.get(
    "/complaints/{complaint_id}",
    response_model=ComplaintResponse,
)
async def get_complaint(
    complaint_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("complaint.create")),
) -> ComplaintResponse:
    """Fetch detail of a single complaint with IDOR protection."""
    authz_repo = AuthorizationRepository(db)
    roles = await authz_repo.get_user_roles(current_user.id, society_id)
    perms = await authz_repo.get_user_permission_codes(current_user.id, society_id)
    has_view_all = any(r.code == "SUPER_ADMIN" for r in roles) or "complaint.view_all" in perms

    service = ComplaintService(db)
    complaint = await service.get_complaint(society_id, complaint_id)

    if not has_view_all and complaint.raised_by_user_id != current_user.id:
        raise ComplaintAccessDeniedError("You are not authorized to view this complaint")

    return ComplaintResponse.model_validate(complaint)


@router.patch(
    "/complaints/{complaint_id}",
    response_model=ComplaintResponse,
)
async def update_complaint(
    complaint_id: UUID,
    data: ComplaintUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("complaint.priority.manage")),
) -> ComplaintResponse:
    """Update complaint details or priority."""
    service = ComplaintService(db)
    complaint = await service.update_complaint(society_id, complaint_id, data)
    return ComplaintResponse.model_validate(complaint)


@router.patch(
    "/complaints/{complaint_id}/priority",
    response_model=ComplaintResponse,
)
async def update_complaint_priority(
    complaint_id: UUID,
    data: ComplaintUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("complaint.priority.manage")),
) -> ComplaintResponse:
    """Update complaint priority level."""
    service = ComplaintService(db)
    complaint = await service.update_complaint(society_id, complaint_id, data)
    return ComplaintResponse.model_validate(complaint)
