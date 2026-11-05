"""API Router for Maintenance Work Orders Core Endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, resolve_society_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.maintenance import MaintenanceWorkOrder
from apps.api.src.database.repositories.authorization_repository import AuthorizationRepository
from apps.api.src.database.session import get_db_session
from apps.api.src.maintenance.application.work_order_service import MaintenanceWorkOrderService
from apps.api.src.maintenance.schemas import (
    WorkOrderCreateRequest,
    WorkOrderResponse,
    WorkOrderScheduleRequest,
    WorkOrderStatusUpdateRequest,
)

router = APIRouter(prefix="/work-orders", tags=["Maintenance Work Orders"])


@router.post("", response_model=WorkOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_work_order(
    request: WorkOrderCreateRequest,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> MaintenanceWorkOrder:
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "maintenance.create" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to create work orders.")

    service = MaintenanceWorkOrderService(db)
    return await service.create_work_order(request, society_id, current_user)


@router.get("", response_model=list[WorkOrderResponse])
async def list_work_orders(
    status: str | None = Query(None),
    priority: str | None = Query(None),
    category_id: uuid.UUID | None = Query(None),
    complaint_id: uuid.UUID | None = Query(None),
    is_overdue: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[MaintenanceWorkOrder]:
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    has_view_all = "maintenance.view_all" in perms

    service = MaintenanceWorkOrderService(db)
    work_orders, _ = await service.list_work_orders(
        society_id=society_id,
        caller=current_user,
        has_view_all=has_view_all,
        status=status,
        priority=priority,
        category_id=category_id,
        complaint_id=complaint_id,
        is_overdue=is_overdue,
        limit=limit,
        offset=offset,
    )
    return work_orders


@router.get("/{work_order_id}", response_model=WorkOrderResponse)
async def get_work_order(
    work_order_id: uuid.UUID,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> MaintenanceWorkOrder:
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    has_view_all = "maintenance.view_all" in perms

    service = MaintenanceWorkOrderService(db)
    return await service.get_work_order(work_order_id, society_id, current_user, has_view_all)


@router.post("/{work_order_id}/schedule", response_model=WorkOrderResponse)
async def schedule_work_order(
    work_order_id: uuid.UUID,
    request: WorkOrderScheduleRequest,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> MaintenanceWorkOrder:
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "maintenance.schedule" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to schedule work orders.")

    service = MaintenanceWorkOrderService(db)
    return await service.update_schedule(work_order_id, society_id, request, current_user)


@router.patch("/{work_order_id}/status", response_model=WorkOrderResponse)
async def update_status(
    work_order_id: uuid.UUID,
    request: WorkOrderStatusUpdateRequest,
    society_id: uuid.UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> MaintenanceWorkOrder:
    auth_repo = AuthorizationRepository(db)
    perms = await auth_repo.get_user_permission_codes(current_user.id, society_id)
    if "maintenance.status.manage" not in perms:
        raise HTTPException(status_code=403, detail="Permission denied to manage work order status.")

    service = MaintenanceWorkOrderService(db)
    return await service.transition_status(work_order_id, society_id, request, current_user)
