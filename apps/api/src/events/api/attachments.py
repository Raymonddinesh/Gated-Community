"""Phase 17 Event Attachments REST Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission
from apps.api.src.database.session import get_db_session
from apps.api.src.events.event_service import EventService
from apps.api.src.events.exceptions import EventNotFoundError
from apps.api.src.events.schemas import (
    EventAttachmentCreate,
    EventAttachmentResponse,
)

router = APIRouter(prefix="/events/{event_id}/attachments", tags=["Event Attachments"])


@router.post("", response_model=EventAttachmentResponse, status_code=status.HTTP_201_CREATED)
async def add_event_attachment(
    request: Request,
    event_id: UUID,
    data: EventAttachmentCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("event.attachment.manage")),
):
    society_id: UUID = request.state.tenant_id
    service = EventService(db)
    try:
        att = await service.add_attachment(society_id, event_id, current_user.id, data)
        return att
    except EventNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e


@router.get("", response_model=list[EventAttachmentResponse])
async def list_event_attachments(
    request: Request,
    event_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("event.view")),
):
    society_id: UUID = request.state.tenant_id
    service = EventService(db)
    return await service.attachment_repo.list_by_event(society_id, event_id)
