"""Phase 20 Communication Providers Registry REST Endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.api.src.auth.dependencies import get_current_user, require_permission
from apps.api.src.notifications.providers.factory import provider_factory

router = APIRouter(prefix="/communication-providers", tags=["Communication Providers"])


class ProviderStatusResponse(BaseModel):
    channel: str
    provider_name: str
    is_active: bool


@router.get("", response_model=list[ProviderStatusResponse])
async def list_providers(
    current_user=Depends(get_current_user),
    _perm=Depends(require_permission("notification.provider.view")),
):
    results = []
    for ch, prov in provider_factory._providers.items():
        results.append(
            ProviderStatusResponse(
                channel=ch,
                provider_name=prov.provider_name,
                is_active=True,
            )
        )
    return results
