"""API Router for Work Order Comments."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, resolve_society_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.maintenance import WorkOrderComment
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.session import get_db_session
from apps.api.src.maintenance.application.comment_service import WorkOrderCommentService
from apps.api.src.maintenance.schemas import (
    WorkOrderCommentCreateRequest,
    WorkOrderCommentResponse,
)

router = APIRouter(prefix="/work-orders/{work_order_id}/comments", tags=["Work Order Comments"])


@router.post("", response_model=WorkOrderCommentResponse, status_code=status.HTTP_201_CREATED)
async def add_comment(
    work_order_id: uuid.UUID,
    request: WorkOrderCommentCreateRequest,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> WorkOrderComment:
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "maintenance.comment" not in perms and "maintenance.comment_internal" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to add comments.")

    has_internal_perm = "maintenance.comment_internal" in perms
    service = WorkOrderCommentService(db)
    return await service.add_comment(work_order_id, society_id, request, current_user, has_internal_perm)


@router.get("", response_model=list[WorkOrderCommentResponse])
async def list_comments(
    work_order_id: uuid.UUID,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[WorkOrderComment]:
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    has_internal_perm = "maintenance.comment_internal" in perms

    service = WorkOrderCommentService(db)
    return await service.list_comments(work_order_id, society_id, current_user, has_internal_perm)
