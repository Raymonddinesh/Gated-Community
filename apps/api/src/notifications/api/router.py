"""Phase 20 Master Notifications Router."""

from fastapi import APIRouter

from apps.api.src.notifications.api.deliveries import router as deliveries_router
from apps.api.src.notifications.api.device_tokens import router as device_tokens_router
from apps.api.src.notifications.api.inbox import router as inbox_router
from apps.api.src.notifications.api.notifications import router as notifications_router
from apps.api.src.notifications.api.preferences import router as preferences_router
from apps.api.src.notifications.api.providers import router as providers_router
from apps.api.src.notifications.api.templates import router as templates_router

router = APIRouter()
router.include_router(inbox_router)
router.include_router(templates_router)
router.include_router(preferences_router)
router.include_router(notifications_router)
router.include_router(deliveries_router)
router.include_router(device_tokens_router)
router.include_router(providers_router)
