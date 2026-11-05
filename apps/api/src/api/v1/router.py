"""API v1 Central Router."""

from fastapi import APIRouter

from apps.api.src.announcements.api.router import router as announcements_router
from apps.api.src.api.v1.endpoints import (
    health,
    platform,
    platform_billing,
    societies,
    society_billing,
    version,
)
from apps.api.src.auth.api.router import router as auth_router
from apps.api.src.billing.api.router import router as billing_router
from apps.api.src.complaints.api.router import router as complaints_router
from apps.api.src.events.api.router import router as events_router
from apps.api.src.facility_asset.api.router import router as facility_asset_router
from apps.api.src.facility_booking.api.router import router as facility_booking_router
from apps.api.src.finance.api.router import router as finance_router
from apps.api.src.governance.api.router import router as governance_router
from apps.api.src.incidents.api.router import router as incidents_router
from apps.api.src.maintenance.api.router import router as maintenance_router
from apps.api.src.notifications.api.router import router as notifications_router
from apps.api.src.residents.api.router import router as residents_router
from apps.api.src.staff.api.router import router as staff_router
from apps.api.src.vehicles.api.router import router as vehicles_router
from apps.api.src.vendor.api.router import router as vendor_router
from apps.api.src.visitors.api.router import router as visitors_router

api_v1_router = APIRouter()

# Mount authentication, system, hierarchy, finance, billing, residents, vehicles, visitors, complaints, maintenance, staff, vendor, facility_asset, facility_booking, announcements, events, governance, incidents, and notifications endpoints
api_v1_router.include_router(auth_router)
api_v1_router.include_router(health.router)
api_v1_router.include_router(version.router)
api_v1_router.include_router(platform.router)
api_v1_router.include_router(platform_billing.router)
api_v1_router.include_router(societies.router)
api_v1_router.include_router(society_billing.router)
api_v1_router.include_router(finance_router)
api_v1_router.include_router(billing_router)
api_v1_router.include_router(residents_router)
api_v1_router.include_router(vehicles_router)
api_v1_router.include_router(visitors_router)
api_v1_router.include_router(complaints_router)
api_v1_router.include_router(maintenance_router)
api_v1_router.include_router(staff_router)
api_v1_router.include_router(vendor_router)
api_v1_router.include_router(facility_asset_router)
api_v1_router.include_router(facility_booking_router)
api_v1_router.include_router(announcements_router)
api_v1_router.include_router(events_router)
api_v1_router.include_router(governance_router)
api_v1_router.include_router(incidents_router)
api_v1_router.include_router(notifications_router)

