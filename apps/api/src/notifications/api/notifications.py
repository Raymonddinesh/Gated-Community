"""Phase 20 Master Notification Creation & Management REST Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission
from apps.api.src.database.session import get_db_session
from apps.api.src.notifications.repositories import NotificationRepository
from apps.api.src.notifications.schemas import (
    NotificationBroadcastCreate,
    NotificationCreate,
    NotificationResponse,
)
from apps.api.src.notifications.services.orchestration_service import OrchestrationService

router = APIRouter(prefix="/notifications", tags=["Notifications Engine"])


@router.post("", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED)
async def create_notification(
    request: Request,
    data: NotificationCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("notification.create")),
):
    society_id: UUID = request.state.tenant_id
    service = OrchestrationService(db)
    notification = await service.create_and_dispatch_notification(
        society_id=society_id,
        category=data.category.value,
        priority=data.priority.value,
        source_domain=data.source_domain,
        source_event_id=data.source_event_id,
        idempotency_key=data.idempotency_key,
        title=data.title,
        content=data.content,
        payload=data.payload,
        sender_id=current_user.id,
        recipient_user_ids=data.recipient_user_ids,
        recipient_type=data.recipient_type.value,
    )
    return NotificationResponse.model_validate(notification)


@router.post("/broadcast", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED)
async def broadcast_notification(
    request: Request,
    data: NotificationBroadcastCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("notification.send")),
):
    society_id: UUID = request.state.tenant_id
    service = OrchestrationService(db)
    notification = await service.create_and_dispatch_notification(
        society_id=society_id,
        category=data.category.value,
        priority=data.priority.value,
        source_domain=data.source_domain,
        title=data.title,
        content=data.content,
        sender_id=current_user.id,
        recipient_type=data.target_type.value,
    )
    return NotificationResponse.model_validate(notification)


@router.get("/{notification_id}", response_model=NotificationResponse)
async def get_notification(
    notification_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("notification.view")),
):
    society_id: UUID = request.state.tenant_id
    repo = NotificationRepository(db)
    notification = await repo.get_by_id(society_id, notification_id)
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    return NotificationResponse.model_validate(notification)
