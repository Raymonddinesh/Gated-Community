"""Phase 20 Mobile Device Tokens REST Endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import get_current_user
from apps.api.src.database.session import get_db_session
from apps.api.src.notifications.repositories import DeviceTokenRepository
from apps.api.src.notifications.schemas import DeviceTokenCreate, DeviceTokenResponse

router = APIRouter(prefix="/notifications/device-tokens", tags=["Device Tokens"])


@router.post("", response_model=DeviceTokenResponse, status_code=status.HTTP_201_CREATED)
async def register_device_token(
    request: Request,
    data: DeviceTokenCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    society_id: UUID = request.state.tenant_id
    repo = DeviceTokenRepository(db)
    token_obj = await repo.register_token(
        society_id=society_id,
        user_id=current_user.id,
        device_token=data.device_token,
        platform=data.platform.value,
    )
    return DeviceTokenResponse.model_validate(token_obj)
