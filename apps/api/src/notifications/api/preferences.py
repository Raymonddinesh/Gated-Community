"""Phase 20 Notification Preferences REST Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user
from apps.api.src.database.session import get_db_session
from apps.api.src.notifications.schemas import (
    ChannelPreferenceResponse,
    ChannelPreferenceUpdate,
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
)
from apps.api.src.notifications.services.preference_service import PreferenceService

router = APIRouter(prefix="/notification-preferences", tags=["Notification Preferences"])


@router.put("", response_model=NotificationPreferenceResponse)
async def update_category_preference(
    request: Request,
    data: NotificationPreferenceUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    society_id: UUID = request.state.tenant_id
    service = PreferenceService(db)
    pref = await service.update_category_preference(
        society_id=society_id,
        user_id=current_user.id,
        category=data.category.value,
        is_enabled=data.is_enabled,
        quiet_hours_enabled=data.quiet_hours_enabled,
        quiet_hours_start=data.quiet_hours_start,
        quiet_hours_end=data.quiet_hours_end,
    )
    return NotificationPreferenceResponse.model_validate(pref)


@router.put("/channels", response_model=ChannelPreferenceResponse)
async def update_channel_preference(
    request: Request,
    data: ChannelPreferenceUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    society_id: UUID = request.state.tenant_id
    service = PreferenceService(db)
    pref = await service.update_channel_preference(
        society_id=society_id,
        user_id=current_user.id,
        category=data.category.value,
        channel=data.channel.value,
        is_enabled=data.is_enabled,
    )
    return ChannelPreferenceResponse.model_validate(pref)
