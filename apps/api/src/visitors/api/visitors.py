"""API Endpoints for Visitor Profile Management."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import (
    require_permission,
    resolve_society_context,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.visitors.application.visitor_service import VisitorService
from apps.api.src.visitors.schemas import (
    VisitorCreateRequest,
    VisitorResponse,
    VisitorStatusUpdateRequest,
    VisitorUpdateRequest,
)

router = APIRouter(tags=["Visitors"])


@router.post("/visitors", response_model=VisitorResponse, status_code=status.HTTP_201_CREATED)
async def register_visitor(
    data: VisitorCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("visitor.create")),
) -> VisitorResponse:
    """Register a new visitor profile into the society."""
    service = VisitorService(db)
    visitor = await service.get_or_create_visitor(society_id, current_user.id, data)
    return VisitorResponse.model_validate(visitor)


@router.get("/visitors", response_model=dict)
async def search_visitors(
    query: str | None = Query(None, description="Search by name, phone, or ID number"),
    visitor_type: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("visitor.view")),
) -> dict:
    """Search and filter visitors."""
    service = VisitorService(db)
    items, total = await service.search(
        society_id=society_id,
        query=query,
        visitor_type=visitor_type,
        status=status_filter,
        page=page,
        size=size,
    )
    return {
        "items": [VisitorResponse.model_validate(v) for v in items],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/visitors/me", response_model=dict)
async def get_my_visitors(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("visitor.view")),
) -> dict:
    """Get visitor invitations created by the current resident."""
    service = VisitorService(db)
    items, total = await service.search_invitations(
        society_id=society_id,
        host_user_id=current_user.id,
        page=page,
        size=size,
    )
    from apps.api.src.visitors.schemas import VisitorInvitationResponse

    return {
        "items": [VisitorInvitationResponse.model_validate(i) for i in items],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/visitors/{visitor_id}", response_model=VisitorResponse)
async def get_visitor(
    visitor_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("visitor.view")),
) -> VisitorResponse:
    """Fetch visitor details by ID."""
    service = VisitorService(db)
    visitor = await service.get_visitor(society_id, visitor_id)
    return VisitorResponse.model_validate(visitor)


@router.patch("/visitors/{visitor_id}", response_model=VisitorResponse)
async def update_visitor(
    visitor_id: UUID,
    data: VisitorUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("visitor.manage")),
) -> VisitorResponse:
    """Update visitor profile details."""
    service = VisitorService(db)
    visitor = await service.update_visitor(society_id, visitor_id, current_user.id, data)
    return VisitorResponse.model_validate(visitor)


@router.patch("/visitors/{visitor_id}/status", response_model=VisitorResponse)
async def update_visitor_status(
    visitor_id: UUID,
    data: VisitorStatusUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("visitor.manage")),
) -> VisitorResponse:
    """Transition visitor status (ACTIVE, BLOCKED, ARCHIVED)."""
    service = VisitorService(db)
    visitor = await service.update_status(society_id, visitor_id, current_user.id, data.status, data.notes)
    return VisitorResponse.model_validate(visitor)
