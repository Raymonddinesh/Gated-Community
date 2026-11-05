"""Main Router for Facility & Asset Management Module."""

from fastapi import APIRouter

from apps.api.src.facility_asset.api.assets import router as assets_router
from apps.api.src.facility_asset.api.categories import router as categories_router
from apps.api.src.facility_asset.api.facilities import router as facilities_router

router = APIRouter(prefix="/facility-asset", tags=["Facility & Asset Management"])

router.include_router(facilities_router)
router.include_router(categories_router)
router.include_router(assets_router)
