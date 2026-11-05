"""Phase 19 Incident Management REST API Router Package."""

from fastapi import APIRouter

from apps.api.src.incidents.api.categories import router as categories_router
from apps.api.src.incidents.api.contacts import router as contacts_router
from apps.api.src.incidents.api.incidents import router as incidents_router

router = APIRouter()
router.include_router(categories_router)
router.include_router(contacts_router)
router.include_router(incidents_router)
