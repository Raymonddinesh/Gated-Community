"""Phase 17 Events REST Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission
from apps.api.src.database.session import get_db_session
from apps.api.src.events.enums import EventStatus, EventType
from apps.api.src.events.event_service import EventService
from apps.api.src.events.exceptions import (
    EventError,
    EventNotFoundError,
    FacilityBookingConflictError,
    InvalidEventStateError,
)
from apps.api.src.events.schemas import (
    EventApprovalRequest,
    EventCancelRequest,
    EventCreate,
    EventMetricsResponse,
    EventResponse,
    EventUpdate,
)

router = APIRouter(prefix="/events", tags=["Events"])


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    request: Request,
    data: EventCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("event.create")),
):
    society_id: UUID = request.state.tenant_id
    service = EventService(db)
    try:
        event = await service.create_event(society_id, current_user.id, data)
        return event
    except EventError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("", response_model=list[EventResponse])
async def list_events(
    request: Request,
    event_status: EventStatus | None = Query(None, alias="status"),
    event_type: EventType | None = Query(None, alias="type"),
    facility_id: UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("event.view")),
):
    society_id: UUID = request.state.tenant_id
    service = EventService(db)
    events = await service.event_repo.list_events(
        society_id,
        status=event_status.value if event_status else None,
        event_type=event_type.value if event_type else None,
        facility_id=facility_id,
        limit=limit,
        offset=offset,
    )
    return events


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    request: Request,
    event_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("event.view")),
):
    society_id: UUID = request.state.tenant_id
    service = EventService(db)
    try:
        event = await service._get_event(society_id, event_id)
        metrics = await service.get_event_metrics(society_id, event_id)
        response = EventResponse.model_validate(event)
        response.metrics = metrics
        return response
    except EventNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e


@router.put("/{event_id}", response_model=EventResponse)
async def update_event(
    request: Request,
    event_id: UUID,
    data: EventUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("event.update")),
):
    society_id: UUID = request.state.tenant_id
    service = EventService(db)
    try:
        return await service.update_event(society_id, event_id, current_user.id, data)
    except EventNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except InvalidEventStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.post("/{event_id}/submit", response_model=EventResponse)
async def submit_event(
    request: Request,
    event_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("event.submit")),
):
    society_id: UUID = request.state.tenant_id
    service = EventService(db)
    try:
        return await service.submit_event(society_id, event_id, current_user.id)
    except EventError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.post("/{event_id}/approve", response_model=EventResponse)
async def approve_event(
    request: Request,
    event_id: UUID,
    data: EventApprovalRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("event.approve")),
):
    society_id: UUID = request.state.tenant_id
    service = EventService(db)
    try:
        if data.action.upper() == "APPROVED":
            return await service.approve_event(society_id, event_id, current_user.id, data.comments)
        else:
            return await service.reject_event(society_id, event_id, current_user.id, data.comments)
    except EventError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.post("/{event_id}/publish", response_model=EventResponse)
async def publish_event(
    request: Request,
    event_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("event.publish")),
):
    society_id: UUID = request.state.tenant_id
    service = EventService(db)
    try:
        return await service.publish_event(society_id, event_id, current_user.id)
    except FacilityBookingConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message) from e
    except EventError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.post("/{event_id}/cancel", response_model=EventResponse)
async def cancel_event(
    request: Request,
    event_id: UUID,
    data: EventCancelRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("event.cancel")),
):
    society_id: UUID = request.state.tenant_id
    service = EventService(db)
    try:
        return await service.cancel_event(society_id, event_id, current_user.id, data.reason)
    except EventError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("/{event_id}/metrics", response_model=EventMetricsResponse)
async def get_event_metrics(
    request: Request,
    event_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("event.view")),
):
    society_id: UUID = request.state.tenant_id
    service = EventService(db)
    try:
        return await service.get_event_metrics(society_id, event_id)
    except EventNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
