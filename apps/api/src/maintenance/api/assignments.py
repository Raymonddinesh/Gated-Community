"""API Router for Work Order Assignments."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, resolve_society_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.maintenance import WorkOrderAssignment
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.session import get_db_session
from apps.api.src.maintenance.application.assignment_service import WorkOrderAssignmentService
from apps.api.src.maintenance.schemas import (
    WorkOrderAssignmentCreateRequest,
    WorkOrderAssignmentResponse,
)

router = APIRouter(prefix="/work-orders/{work_order_id}/assignments", tags=["Work Order Assignments"])


@router.post("", response_model=WorkOrderAssignmentResponse, status_code=status.HTTP_201_CREATED)
async def assign_work_order(
    work_order_id: uuid.UUID,
    request: WorkOrderAssignmentCreateRequest,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> WorkOrderAssignment:
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "maintenance.assign" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to assign work orders.")

    service = WorkOrderAssignmentService(db)
    return await service.assign_work_order(work_order_id, society_id, request, current_user)
