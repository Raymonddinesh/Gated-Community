"""API Router for Work Order Resolution & Verification Lifecycle."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, resolve_society_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.maintenance import MaintenanceWorkOrder, WorkOrderResolution
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.session import get_db_session
from apps.api.src.maintenance.application.resolution_service import WorkOrderResolutionService
from apps.api.src.maintenance.schemas import (
    WorkOrderResolutionCreateRequest,
    WorkOrderResolutionResponse,
    WorkOrderResolutionVerifyRequest,
    WorkOrderResponse,
)

router = APIRouter(prefix="/work-orders/{work_order_id}", tags=["Work Order Resolution"])


@router.post("/complete", response_model=WorkOrderResolutionResponse, status_code=status.HTTP_201_CREATED)
async def complete_work_order(
    work_order_id: uuid.UUID,
    request: WorkOrderResolutionCreateRequest,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> WorkOrderResolution:
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "maintenance.resolve" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to resolve work orders.")

    service = WorkOrderResolutionService(db)
    return await service.complete_work_order(work_order_id, society_id, request, current_user)


@router.post("/verify", response_model=WorkOrderResolutionResponse)
async def verify_resolution(
    work_order_id: uuid.UUID,
    request: WorkOrderResolutionVerifyRequest,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> WorkOrderResolution:
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "maintenance.verify" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to verify resolution.")

    service = WorkOrderResolutionService(db)
    return await service.verify_resolution(work_order_id, society_id, request, current_user)


@router.post("/close", response_model=WorkOrderResponse)
async def close_work_order(
    work_order_id: uuid.UUID,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> MaintenanceWorkOrder:
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "maintenance.close" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to close work orders.")

    service = WorkOrderResolutionService(db)
    return await service.close_work_order(work_order_id, society_id, current_user)
