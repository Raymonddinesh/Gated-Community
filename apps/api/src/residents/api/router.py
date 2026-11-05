"""Resident and Occupancy Master API Router."""

from fastapi import APIRouter

from apps.api.src.residents.api import (
    household,
    occupancies,
    ownerships,
    residents,
)

router = APIRouter()

router.include_router(residents.router)
router.include_router(occupancies.router)
router.include_router(ownerships.router)
router.include_router(household.router)
