"""Aggregated Router for Vehicle Management and Access Control."""

from fastapi import APIRouter

from apps.api.src.vehicles.api.access import router as access_router
from apps.api.src.vehicles.api.associations import router as associations_router
from apps.api.src.vehicles.api.documents import router as documents_router
from apps.api.src.vehicles.api.vehicles import router as vehicles_router

router = APIRouter()

router.include_router(vehicles_router)
router.include_router(associations_router)
router.include_router(documents_router)
router.include_router(access_router)
