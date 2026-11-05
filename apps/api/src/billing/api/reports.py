"""Billing and Financial Obligations Reporting API Endpoints."""

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import require_permission, resolve_society_context
from apps.api.src.billing.application.report_service import BillingReportService
from apps.api.src.billing.schemas import (
    AgingReportResponse,
    CollectionSummaryResponse,
    ResidentOutstandingResponse,
    UnitOutstandingResponse,
)
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session

router = APIRouter(prefix="/societies/{society_id}/billing/reports", tags=["Billing - Reports"])


@router.get("/collection-summary", response_model=CollectionSummaryResponse)
async def get_collection_summary(
    society_id: UUID,
    period_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("billing.reports.view")),
) -> CollectionSummaryResponse:
    """Aggregate billing, collections, adjustments, and outstanding revenue summary."""
    service = BillingReportService(db)
    data = await service.get_collection_summary(society_id, period_id)
    return CollectionSummaryResponse.model_validate(data)


@router.get("/unit-outstanding", response_model=list[UnitOutstandingResponse])
async def get_unit_wise_outstanding(
    society_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("billing.reports.view")),
) -> list[UnitOutstandingResponse]:
    """Outstanding balance grouped by physical unit."""
    service = BillingReportService(db)
    data = await service.get_unit_wise_outstanding(society_id)
    return [UnitOutstandingResponse.model_validate(r) for r in data]


@router.get("/resident-outstanding", response_model=list[ResidentOutstandingResponse])
async def get_resident_wise_outstanding(
    society_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("billing.reports.view")),
) -> list[ResidentOutstandingResponse]:
    """Outstanding balance grouped by responsible resident user."""
    service = BillingReportService(db)
    data = await service.get_resident_wise_outstanding(society_id)
    return [ResidentOutstandingResponse.model_validate(r) for r in data]


@router.get("/aging", response_model=AgingReportResponse)
async def get_aging_report(
    society_id: UUID,
    as_of_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("billing.reports.view")),
) -> AgingReportResponse:
    """Aging breakdown of outstanding maintenance dues into standard time buckets."""
    service = BillingReportService(db)
    data = await service.get_aging_report(society_id, as_of_date)
    return AgingReportResponse.model_validate(data)


@router.get("/payment-methods")
async def get_payment_method_summary(
    society_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("billing.reports.view")),
) -> list[dict[str, Any]]:
    """Summary of collections categorized by recorded payment method."""
    service = BillingReportService(db)
    return await service.get_payment_method_summary(society_id)


@router.get("/unallocated-payments")
async def get_unallocated_payments(
    society_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("billing.reports.view")),
) -> list[dict[str, Any]]:
    """Listing of payments with remaining unallocated / advance balances."""
    service = BillingReportService(db)
    return await service.get_unallocated_payments_report(society_id)
