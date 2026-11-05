"""API Router for Work Order Material Usages."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, resolve_society_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.maintenance import WorkOrderMaterialUsage
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.session import get_db_session
from apps.api.src.maintenance.application.material_service import WorkOrderMaterialService
from apps.api.src.maintenance.schemas import (
    WorkOrderMaterialUsageCreateRequest,
    WorkOrderMaterialUsageResponse,
)

router = APIRouter(prefix="/work-orders/{work_order_id}/materials", tags=["Work Order Materials"])


@router.get("", response_model=list[WorkOrderMaterialUsageResponse])
async def list_materials(
    work_order_id: uuid.UUID,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[WorkOrderMaterialUsage]:
    service = WorkOrderMaterialService(db)
    return await service.list_materials(work_order_id, society_id)


@router.post("", response_model=WorkOrderMaterialUsageResponse, status_code=status.HTTP_201_CREATED)
async def add_material_usage(
    work_order_id: uuid.UUID,
    request: WorkOrderMaterialUsageCreateRequest,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> WorkOrderMaterialUsage:
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "maintenance.material.manage" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to manage materials.")

    service = WorkOrderMaterialService(db)
    return await service.add_material_usage(work_order_id, society_id, request, current_user)
