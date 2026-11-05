"""API Endpoints for Pre-Approved Visitor Invitations."""

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
    VisitorInvitationCreateRequest,
    VisitorInvitationResponse,
)

router = APIRouter(tags=["Visitor Invitations"])


@router.post(
    "/visitors/invitations", response_model=VisitorInvitationResponse, status_code=status.HTTP_201_CREATED
)
async def create_invitation(
    data: VisitorInvitationCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("visitor.invite")),
) -> VisitorInvitationResponse:
    """Create a pre-approved visitor invitation by resident host."""
    service = VisitorService(db)
    invitation = await service.create_invitation(society_id, current_user.id, data)
    return VisitorInvitationResponse.model_validate(invitation)


@router.get("/visitors/invitations", response_model=dict)
async def list_invitations(
    unit_id: UUID | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("visitor.view")),
) -> dict:
    """Search invitations for a society or unit."""
    service = VisitorService(db)
    items, total = await service.search_invitations(
        society_id=society_id,
        unit_id=unit_id,
        status=status_filter,
        page=page,
        size=size,
    )
    return {
        "items": [VisitorInvitationResponse.model_validate(i) for i in items],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/visitors/invitations/{invitation_id}", response_model=VisitorInvitationResponse)
async def get_invitation(
    invitation_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("visitor.view")),
) -> VisitorInvitationResponse:
    """Fetch single invitation by ID."""
    service = VisitorService(db)
    inv = await service.get_invitation(society_id, invitation_id)
    return VisitorInvitationResponse.model_validate(inv)


@router.post("/visitors/invitations/{invitation_id}/cancel", response_model=VisitorInvitationResponse)
async def cancel_invitation(
    invitation_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("visitor.invite")),
) -> VisitorInvitationResponse:
    """Cancel a pending/approved invitation."""
    service = VisitorService(db)
    inv = await service.cancel_invitation(society_id, invitation_id, current_user.id)
    return VisitorInvitationResponse.model_validate(inv)
