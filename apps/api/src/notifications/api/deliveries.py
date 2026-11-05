"""Phase 20 Notification Deliveries REST Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission
from apps.api.src.database.session import get_db_session
from apps.api.src.notifications.repositories import DeliveryRepository
from apps.api.src.notifications.schemas import DeliveryResponse

router = APIRouter(prefix="/notification-deliveries", tags=["Notification Deliveries"])


@router.get("/{notification_id}", response_model=list[DeliveryResponse])
async def get_deliveries(
    notification_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("notification.delivery.view")),
):
    society_id: UUID = request.state.tenant_id
    repo = DeliveryRepository(db)
    deliveries = await repo.get_deliveries_by_notification(society_id, notification_id)
    return [DeliveryResponse.model_validate(d) for d in deliveries]
