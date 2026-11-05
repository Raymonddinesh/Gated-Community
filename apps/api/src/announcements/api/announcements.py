"""Announcement Core REST API Router."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.announcements.announcement_service import AnnouncementService
from apps.api.src.announcements.enums import AnnouncementPriority, AnnouncementStatus
from apps.api.src.announcements.schemas import (
    AnnouncementAcknowledgementResponse,
    AnnouncementCreate,
    AnnouncementListResponse,
    AnnouncementMetricsResponse,
    AnnouncementResponse,
    AnnouncementScheduleCreate,
    AnnouncementStatusHistoryResponse,
    AnnouncementUpdate,
)
from apps.api.src.auth.dependencies import get_current_user, require_permission, resolve_society_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session

router = APIRouter(prefix="/announcements", tags=["Announcements"])


@router.post(
    "",
    response_model=AnnouncementResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("announcement.create"))],
)
async def create_announcement(
    payload: AnnouncementCreate,
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = AnnouncementService(db)
    return await service.create_announcement(society_id, current_user.id, payload)


@router.get(
    "",
    response_model=AnnouncementListResponse,
    dependencies=[Depends(require_permission("announcement.view"))],
)
async def list_announcements(
    status: AnnouncementStatus | None = Query(None),
    priority: AnnouncementPriority | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = AnnouncementService(db)
    items, total = await service.list_announcements_for_user(
        society_id=society_id,
        user_id=current_user.id,
        status=status,
        priority=priority,
        page=page,
        size=size,
    )
    return AnnouncementListResponse(
        items=[AnnouncementResponse.model_validate(a) for a in items],
        total=total,
        page=page,
        size=size,
    )


@router.get(
    "/{announcement_id}",
    response_model=AnnouncementResponse,
    dependencies=[Depends(require_permission("announcement.view"))],
)
async def get_announcement(
    announcement_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = AnnouncementService(db)
    return await service.get_announcement(society_id, announcement_id, current_user.id)


@router.put(
    "/{announcement_id}",
    response_model=AnnouncementResponse,
    dependencies=[Depends(require_permission("announcement.update"))],
)
async def update_announcement(
    announcement_id: UUID,
    payload: AnnouncementUpdate,
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = AnnouncementService(db)
    return await service.update_announcement(society_id, announcement_id, current_user.id, payload)


@router.post(
    "/{announcement_id}/submit",
    response_model=AnnouncementResponse,
    dependencies=[Depends(require_permission("announcement.submit"))],
)
async def submit_announcement(
    announcement_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = AnnouncementService(db)
    return await service.submit_announcement(society_id, announcement_id, current_user.id)


@router.post(
    "/{announcement_id}/approve",
    response_model=AnnouncementResponse,
    dependencies=[Depends(require_permission("announcement.approve"))],
)
async def approve_announcement(
    announcement_id: UUID,
    reason: str | None = Query(None),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = AnnouncementService(db)
    return await service.approve_announcement(society_id, announcement_id, current_user.id, reason)


@router.post(
    "/{announcement_id}/reject",
    response_model=AnnouncementResponse,
    dependencies=[Depends(require_permission("announcement.reject"))],
)
async def reject_announcement(
    announcement_id: UUID,
    reason: str | None = Query(None),
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = AnnouncementService(db)
    return await service.reject_announcement(society_id, announcement_id, current_user.id, reason)


@router.post(
    "/{announcement_id}/publish",
    response_model=AnnouncementResponse,
    dependencies=[Depends(require_permission("announcement.publish"))],
)
async def publish_announcement(
    announcement_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = AnnouncementService(db)
    return await service.publish_announcement(society_id, announcement_id, current_user.id)


@router.post(
    "/{announcement_id}/schedule",
    response_model=AnnouncementResponse,
    dependencies=[Depends(require_permission("announcement.schedule"))],
)
async def schedule_announcement(
    announcement_id: UUID,
    payload: AnnouncementScheduleCreate,
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = AnnouncementService(db)
    return await service.schedule_announcement(society_id, announcement_id, current_user.id, payload)


@router.post(
    "/{announcement_id}/expire",
    response_model=AnnouncementResponse,
    dependencies=[Depends(require_permission("announcement.expire"))],
)
async def expire_announcement(
    announcement_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = AnnouncementService(db)
    return await service.expire_announcement(society_id, announcement_id, current_user.id)


@router.post(
    "/{announcement_id}/archive",
    response_model=AnnouncementResponse,
    dependencies=[Depends(require_permission("announcement.archive"))],
)
async def archive_announcement(
    announcement_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = AnnouncementService(db)
    return await service.archive_announcement(society_id, announcement_id, current_user.id)


@router.post(
    "/{announcement_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("announcement.view"))],
)
async def mark_announcement_as_read(
    announcement_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = AnnouncementService(db)
    await service.mark_as_read(society_id, announcement_id, current_user.id)


@router.post(
    "/{announcement_id}/acknowledge",
    response_model=AnnouncementAcknowledgementResponse,
    dependencies=[Depends(require_permission("announcement.view"))],
)
async def acknowledge_announcement(
    announcement_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    service = AnnouncementService(db)
    return await service.acknowledge_announcement(society_id, announcement_id, current_user.id)


@router.get(
    "/{announcement_id}/metrics",
    response_model=AnnouncementMetricsResponse,
    dependencies=[Depends(require_permission("announcement.read_receipt.view"))],
)
async def get_announcement_metrics(
    announcement_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = AnnouncementService(db)
    return await service.get_metrics(society_id, announcement_id)


@router.get(
    "/{announcement_id}/audit-trail",
    response_model=list[AnnouncementStatusHistoryResponse],
    dependencies=[Depends(require_permission("announcement.audit.view"))],
)
async def get_announcement_audit_trail(
    announcement_id: UUID,
    society_id: UUID = Depends(resolve_society_context),
    db: AsyncSession = Depends(get_db_session),
):
    service = AnnouncementService(db)
    return await service.history_repo.list_by_announcement(society_id, announcement_id)
