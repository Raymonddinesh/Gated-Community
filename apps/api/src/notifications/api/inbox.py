"""Phase 20 Notification Inbox REST Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user
from apps.api.src.database.session import get_db_session
from apps.api.src.notifications.exceptions import RecipientNotFoundError
from apps.api.src.notifications.schemas import InboxItemResponse, UnreadCountResponse
from apps.api.src.notifications.services.inbox_service import InboxService

router = APIRouter(prefix="/notifications/inbox", tags=["Notification Inbox"])


@router.get("", response_model=list[InboxItemResponse])
async def get_inbox(
    request: Request,
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    society_id: UUID = request.state.tenant_id
    service = InboxService(db)
    return await service.get_user_inbox(
        society_id=society_id,
        user_id=current_user.id,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    society_id: UUID = request.state.tenant_id
    service = InboxService(db)
    count = await service.get_unread_count(society_id, current_user.id)
    return UnreadCountResponse(unread_count=count)


@router.post("/{recipient_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_item_read(
    recipient_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    society_id: UUID = request.state.tenant_id
    service = InboxService(db)
    try:
        await service.mark_as_read(society_id, current_user.id, recipient_id)
    except RecipientNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/read-all", response_model=UnreadCountResponse)
async def mark_all_read(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    society_id: UUID = request.state.tenant_id
    service = InboxService(db)
    updated_count = await service.mark_all_as_read(society_id, current_user.id)
    return UnreadCountResponse(unread_count=updated_count)
