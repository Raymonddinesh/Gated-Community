"""Main Router for Vendor & Service Provider Management Module."""

from fastapi import APIRouter

from apps.api.src.vendor.api.categories import router as categories_router
from apps.api.src.vendor.api.documents import router as documents_router
from apps.api.src.vendor.api.services import router as services_router
from apps.api.src.vendor.api.vendors import router as vendors_router

router = APIRouter(prefix="/vendors", tags=["Vendor Management"])

router.include_router(categories_router)
router.include_router(vendors_router)
router.include_router(services_router)
router.include_router(documents_router)
