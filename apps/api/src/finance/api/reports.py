"""Financial Reports and Statements API endpoints."""

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import require_permission, resolve_society_context
from apps.api.src.core.exceptions import NotFoundException
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.finance.application.report_service import ReportService
from apps.api.src.finance.infrastructure.repositories import FinancialReportRepository
from apps.api.src.finance.schemas import (
    FinancialReportResponse,
    ReportGenerateRequest,
)

router = APIRouter(prefix="/societies/{society_id}/finance/reports", tags=["Finance - Reports & Statements"])


@router.get("/trial-balance")
async def get_trial_balance(
    society_id: UUID,
    financial_period_id: UUID = Query(..., description="Financial period ID"),
    as_of_date: date | None = Query(None, description="Optional cut-off date"),
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("finance.read")),
) -> dict[str, Any]:
    """Calculate deterministic Trial Balance proving total debits == total credits."""
    service = ReportService(db)
    return await service.generate_trial_balance(
        society_id=society_id,
        financial_period_id=financial_period_id,
        as_of_date=as_of_date,
    )


@router.get("/general-ledger")
async def get_general_ledger(
    society_id: UUID,
    account_id: UUID = Query(..., description="Account ID to inspect ledger for"),
    financial_period_id: UUID | None = Query(None, description="Optional period ID"),
    from_date: date | None = Query(None, description="Start date"),
    to_date: date | None = Query(None, description="End date"),
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("finance.read")),
) -> dict[str, Any]:
    """Retrieve full chronological transaction activity and running balance for an account."""
    service = ReportService(db)
    return await service.generate_general_ledger(
        society_id=society_id,
        account_id=account_id,
        financial_period_id=financial_period_id,
        from_date=from_date,
        to_date=to_date,
    )


@router.get("/income-expenditure")
async def get_income_expenditure(
    society_id: UUID,
    financial_period_id: UUID = Query(..., description="Financial period ID"),
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("finance.read")),
) -> dict[str, Any]:
    """Calculate deterministic Income and Expenditure Statement showing Net Surplus / Deficit."""
    service = ReportService(db)
    return await service.generate_income_and_expenditure(
        society_id=society_id,
        financial_period_id=financial_period_id,
    )


@router.get("/balance-sheet")
async def get_balance_sheet(
    society_id: UUID,
    financial_period_id: UUID = Query(..., description="Financial period ID"),
    as_of_date: date | None = Query(None, description="Optional as of date"),
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("finance.read")),
) -> dict[str, Any]:
    """Calculate deterministic Balance Sheet proving Total Assets == Total Liabilities + Total Equity."""
    service = ReportService(db)
    return await service.generate_balance_sheet(
        society_id=society_id,
        financial_period_id=financial_period_id,
        as_of_date=as_of_date,
    )


@router.get("/receipts-payments")
async def get_receipts_payments(
    society_id: UUID,
    financial_period_id: UUID = Query(..., description="Financial period ID"),
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("finance.read")),
) -> dict[str, Any]:
    """Calculate cash and bank receipts and disbursements statement."""
    service = ReportService(db)
    return await service.generate_receipts_and_payments(
        society_id=society_id,
        financial_period_id=financial_period_id,
    )


@router.post("/generate", response_model=FinancialReportResponse, status_code=201)
async def generate_and_save_report(
    society_id: UUID,
    payload: ReportGenerateRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("finance.report.generate")),
) -> FinancialReportResponse:
    """Generate, version, and snapshot a financial report."""
    service = ReportService(db)
    report_name = payload.name or f"{payload.report_type.replace('_', ' ').title()} Report"
    report = await service.save_and_publish_report(
        society_id=society_id,
        financial_period_id=payload.financial_period_id,
        report_type=payload.report_type,
        name=report_name,
        user_id=current_user.id,
        publish_immediately=payload.publish_immediately,
    )
    return FinancialReportResponse.model_validate(report)


@router.get("", response_model=list[FinancialReportResponse])
async def list_saved_reports(
    society_id: UUID,
    report_type: str | None = Query(None, description="Filter by report type"),
    period_id: UUID | None = Query(None, description="Filter by period ID"),
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("finance.read")),
) -> list[FinancialReportResponse]:
    """List persisted financial report snapshots."""
    repo = FinancialReportRepository(db)
    reports = await repo.list_reports(society_id, report_type=report_type, period_id=period_id)
    return [FinancialReportResponse.model_validate(r) for r in reports]


@router.get("/{report_id}", response_model=FinancialReportResponse)
async def get_saved_report(
    society_id: UUID,
    report_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("finance.read")),
) -> FinancialReportResponse:
    """Retrieve an immutable financial report snapshot."""
    repo = FinancialReportRepository(db)
    report = await repo.get_by_id(report_id, society_id)
    if not report:
        raise NotFoundException(f"Financial report '{report_id}' not found.")
    return FinancialReportResponse.model_validate(report)
