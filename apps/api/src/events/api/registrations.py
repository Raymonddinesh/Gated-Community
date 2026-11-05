"""Phase 17 Event Registrations REST Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission
from apps.api.src.database.session import get_db_session
from apps.api.src.events.event_service import EventService
from apps.api.src.events.exceptions import (
    DuplicateRegistrationError,
    EventError,
    EventNotFoundError,
)
from apps.api.src.events.participant_privacy import EventParticipantPrivacyFilter
from apps.api.src.events.schemas import (
    EventRegistrationCreate,
    EventRegistrationResponse,
)

router = APIRouter(prefix="/events/{event_id}/registrations", tags=["Event Registrations"])


@router.post("", response_model=EventRegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register_for_event(
    request: Request,
    event_id: UUID,
    data: EventRegistrationCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("event.view")),
):
    society_id: UUID = request.state.tenant_id
    service = EventService(db)
    try:
        reg = await service.register_participant(society_id, event_id, current_user.id, data)
        return reg
    except DuplicateRegistrationError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.message) from e
    except EventError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.post("/cancel", response_model=EventRegistrationResponse)
async def cancel_my_registration(
    request: Request,
    event_id: UUID,
    reason: str | None = Query(None),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("event.view")),
):
    society_id: UUID = request.state.tenant_id
    service = EventService(db)
    try:
        reg = await service.cancel_registration(society_id, event_id, current_user.id, reason)
        return reg
    except EventNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except EventError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("", response_model=list[EventRegistrationResponse])
async def list_event_registrations(
    request: Request,
    event_id: UUID,
    registration_status: str | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("event.registration.view")),
):
    society_id: UUID = request.state.tenant_id
    service = EventService(db)
    registrations = await service.registration_repo.list_by_event(
        society_id, event_id, status=registration_status, limit=limit, offset=offset
    )

    # Privacy filtering for non-admin viewers
    has_manage_perm = "event.registration.manage" in getattr(current_user, "permissions", [])
    raw_dicts = [EventRegistrationResponse.model_validate(r).model_dump() for r in registrations]
    filtered_dicts = EventParticipantPrivacyFilter.filter_participant_details(
        raw_dicts, current_user.id, has_manage_perm
    )
    return [EventRegistrationResponse.model_validate(d) for d in filtered_dicts]
