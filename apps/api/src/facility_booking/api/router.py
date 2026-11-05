"""Main Router for Facility Booking Management Module."""

from fastapi import APIRouter

from apps.api.src.facility_booking.api.blackouts import router as blackouts_router
from apps.api.src.facility_booking.api.bookings import router as bookings_router
from apps.api.src.facility_booking.api.configs import router as configs_router

router = APIRouter(tags=["Facility Booking Management"])

router.include_router(configs_router)
router.include_router(blackouts_router)
router.include_router(bookings_router)
