"""API Router for Complaint Comments & Communications."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import (
    require_permission,
    resolve_society_context,
)
from apps.api.src.complaints.application.comment_service import ComplaintCommentService
from apps.api.src.complaints.schemas import (
    ComplaintCommentCreateRequest,
    ComplaintCommentResponse,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.session import get_db_session

router = APIRouter(tags=["Complaint Comments"])


@router.post(
    "/complaints/{complaint_id}/comments",
    response_model=ComplaintCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_comment(
    complaint_id: UUID,
    data: ComplaintCommentCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("complaint.comment")),
) -> ComplaintCommentResponse:
    """Post a public or internal comment on a complaint."""
    authz_repo = AuthorizationRepository(db)
    roles = await authz_repo.get_user_roles(current_user.id, society_id)
    perms = await authz_repo.get_user_permission_codes(current_user.id, society_id)
    has_internal_perm = any(r.code == "SUPER_ADMIN" for r in roles) or "complaint.comment_internal" in perms

    service = ComplaintCommentService(db)
    comment = await service.add_comment(
        society_id=society_id,
        complaint_id=complaint_id,
        author_user_id=current_user.id,
        data=data,
        is_staff_or_admin=has_internal_perm,
    )
    return ComplaintCommentResponse.model_validate(comment)


@router.get(
    "/complaints/{complaint_id}/comments",
    response_model=list[ComplaintCommentResponse],
)
async def list_comments(
    complaint_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("complaint.comment")),
) -> list[ComplaintCommentResponse]:
    """List comments for a complaint (hides INTERNAL comments from residents)."""
    authz_repo = AuthorizationRepository(db)
    roles = await authz_repo.get_user_roles(current_user.id, society_id)
    perms = await authz_repo.get_user_permission_codes(current_user.id, society_id)
    has_internal_perm = any(r.code == "SUPER_ADMIN" for r in roles) or "complaint.comment_internal" in perms

    service = ComplaintCommentService(db)
    comments = await service.list_comments(
        society_id=society_id,
        complaint_id=complaint_id,
        include_internal=has_internal_perm,
    )
    return [ComplaintCommentResponse.model_validate(c) for c in comments]
