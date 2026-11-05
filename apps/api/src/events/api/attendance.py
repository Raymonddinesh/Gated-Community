"""Phase 17 Event Attendance REST Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission
from apps.api.src.database.session import get_db_session
from apps.api.src.events.event_service import EventService
from apps.api.src.events.exceptions import AttendanceNotAllowedError, EventError, EventNotFoundError
from apps.api.src.events.schemas import (
    EventAttendanceRecord,
    EventAttendanceResponse,
)

router = APIRouter(prefix="/events/{event_id}/attendance", tags=["Event Attendance"])


@router.post("/{user_id}", response_model=EventAttendanceResponse)
async def record_attendance(
    request: Request,
    event_id: UUID,
    user_id: UUID,
    data: EventAttendanceRecord,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("event.attendance.manage")),
):
    society_id: UUID = request.state.tenant_id
    service = EventService(db)
    try:
        att = await service.record_attendance(
            society_id, event_id, user_id, current_user.id, data.status, data.notes
        )
        return att
    except EventNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except AttendanceNotAllowedError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e
    except EventError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("", response_model=list[EventAttendanceResponse])
async def list_attendance(
    request: Request,
    event_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("event.attendance.view")),
):
    society_id: UUID = request.state.tenant_id
    service = EventService(db)
    return await service.attendance_repo.list_by_event(society_id, event_id)
