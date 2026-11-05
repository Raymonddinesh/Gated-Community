"""Phase 18 Governance Meeting REST Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user, require_permission
from apps.api.src.database.session import get_db_session
from apps.api.src.governance.enums import MeetingStatus, MeetingType
from apps.api.src.governance.exceptions import GovernanceError, GovernanceNotFoundError
from apps.api.src.governance.governance_service import GovernanceService
from apps.api.src.governance.schemas import (
    MeetingAgendaItemCreate,
    MeetingAgendaItemResponse,
    MeetingAttendanceRecord,
    MeetingAttendanceResponse,
    MeetingCreate,
    MeetingQuorumRecord,
    MeetingQuorumResponse,
    MeetingResponse,
    MeetingStateTransition,
    MeetingUpdate,
)

router = APIRouter(prefix="/governance/meetings", tags=["Governance Meetings"])


@router.post("", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    request: Request,
    data: MeetingCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("meeting.create")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        meeting = await service.create_meeting(society_id, current_user.id, data)
        return meeting
    except GovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("", response_model=list[MeetingResponse])
async def list_meetings(
    request: Request,
    committee_id: UUID | None = Query(None),
    meeting_type: MeetingType | None = Query(None, alias="type"),
    meeting_status: MeetingStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("meeting.view")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    meetings = await service.list_meetings(
        society_id=society_id,
        committee_id=committee_id,
        meeting_type=meeting_type,
        meeting_status=meeting_status,
        limit=limit,
        offset=offset,
    )
    return meetings


@router.get("/{meeting_id}", response_model=MeetingResponse)
async def get_meeting(
    request: Request,
    meeting_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("meeting.view")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        meeting = await service.get_meeting(society_id, meeting_id)
        return meeting
    except GovernanceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e


@router.patch("/{meeting_id}", response_model=MeetingResponse)
async def update_meeting(
    request: Request,
    meeting_id: UUID,
    data: MeetingUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("meeting.update")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        meeting = await service.update_meeting(society_id, meeting_id, data)
        return meeting
    except GovernanceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except GovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.post("/{meeting_id}/transition", response_model=MeetingResponse)
async def transition_meeting_status(
    request: Request,
    meeting_id: UUID,
    transition: MeetingStateTransition,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("meeting.status.manage")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        meeting = await service.transition_meeting_status(society_id, meeting_id, transition, current_user.id)
        return meeting
    except GovernanceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except GovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


# Agenda Items
@router.post(
    "/{meeting_id}/agenda", response_model=MeetingAgendaItemResponse, status_code=status.HTTP_201_CREATED
)
async def add_agenda_item(
    request: Request,
    meeting_id: UUID,
    data: MeetingAgendaItemCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("meeting.update")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        item = await service.add_agenda_item(society_id, meeting_id, data)
        return item
    except GovernanceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except GovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("/{meeting_id}/agenda", response_model=list[MeetingAgendaItemResponse])
async def list_agenda_items(
    request: Request,
    meeting_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("meeting.view")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    items = await service.list_agenda_items(society_id, meeting_id)
    return items


# Quorum
@router.post("/{meeting_id}/quorum", response_model=MeetingQuorumResponse)
async def record_quorum(
    request: Request,
    meeting_id: UUID,
    data: MeetingQuorumRecord,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("quorum.manage")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        quorum = await service.record_quorum(society_id, meeting_id, data, recorded_by=current_user.id)
        return quorum
    except GovernanceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except GovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("/{meeting_id}/quorum", response_model=MeetingQuorumResponse | None)
async def get_quorum(
    request: Request,
    meeting_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("meeting.view")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    quorum = await service.get_quorum(society_id, meeting_id)
    return quorum


# Attendance
@router.post("/{meeting_id}/attendance", response_model=MeetingAttendanceResponse)
async def record_attendance(
    request: Request,
    meeting_id: UUID,
    data: MeetingAttendanceRecord,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("meeting.update")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    try:
        attendance = await service.record_attendance(
            society_id, meeting_id, data, recorded_by=current_user.id
        )
        return attendance
    except GovernanceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.message) from e
    except GovernanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message) from e


@router.get("/{meeting_id}/attendance", response_model=list[MeetingAttendanceResponse])
async def list_attendance(
    request: Request,
    meeting_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("meeting.view")),
):
    society_id: UUID = request.state.tenant_id
    service = GovernanceService(db)
    records = await service.list_attendance(society_id, meeting_id)
    return records
