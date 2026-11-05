"""Accounting Configuration, Provider, and Import/Export API endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.auth.dependencies import require_permission, resolve_society_context
from apps.api.src.database.models.identity import User
from apps.api.src.database.session import get_db_session
from apps.api.src.finance.infrastructure.repositories import AccountingConfigRepository
from apps.api.src.finance.providers.base import JournalEntryDTO, JournalLineDTO
from apps.api.src.finance.providers.factory import get_accounting_provider
from apps.api.src.finance.providers.import_export import ImportExportProvider
from apps.api.src.finance.schemas import (
    AccountingConfigResponse,
    AccountingConfigUpdateRequest,
    JournalImportRequest,
    ProviderResultResponse,
)

router = APIRouter(prefix="/societies/{society_id}/finance", tags=["Finance - Config & Integration"])


@router.get("/config", response_model=AccountingConfigResponse)
async def get_accounting_config(
    society_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("finance.read")),
) -> AccountingConfigResponse:
    """Retrieve accounting configuration and integration status for a society."""
    repo = AccountingConfigRepository(db)
    config = await repo.get_by_society_id(society_id)
    if not config:
        # Create default NATIVE config if not found
        config = await repo.create_config(society_id=society_id, accounting_mode="NATIVE")
        await db.commit()
        await db.refresh(config)
    return AccountingConfigResponse.model_validate(config)


@router.patch("/config", response_model=AccountingConfigResponse)
async def update_accounting_config(
    society_id: UUID,
    payload: AccountingConfigUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("finance.account.manage")),
) -> AccountingConfigResponse:
    """Update accounting configuration (mode, authoritative source, Tally info)."""
    repo = AccountingConfigRepository(db)
    config = await repo.update_config(
        society_id=society_id,
        accounting_mode=payload.accounting_mode,
        authoritative_source=payload.authoritative_source,
        tally_company_name=payload.tally_company_name,
        tally_guid=payload.tally_guid,
    )
    return AccountingConfigResponse.model_validate(config)


@router.get("/provider/health")
async def check_provider_health(
    society_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("finance.read")),
) -> dict[str, Any]:
    """Verify health and connectivity of the active accounting provider."""
    provider = await get_accounting_provider(db, society_id)
    is_healthy = await provider.health_check(society_id)
    repo = AccountingConfigRepository(db)
    config = await repo.get_by_society_id(society_id)
    mode = config.accounting_mode if config else "NATIVE"
    return {
        "society_id": str(society_id),
        "accounting_mode": mode,
        "is_healthy": is_healthy,
        "provider_type": provider.__class__.__name__,
    }


@router.post("/import", response_model=ProviderResultResponse)
async def import_journal_entries(
    society_id: UUID,
    payload: JournalImportRequest,
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    current_user: User = Depends(require_permission("finance.journal.create")),
) -> ProviderResultResponse:
    """Validate or import batch journal entries."""
    provider = await get_accounting_provider(db, society_id)
    # Convert payload entries to DTOs
    dtos: list[JournalEntryDTO] = []
    for entry in payload.entries:
        lines = [
            JournalLineDTO(
                account_code=line.account_code,
                debit_amount=line.debit_amount,
                credit_amount=line.credit_amount,
                description=line.description,
            )
            for line in entry.lines
        ]
        dtos.append(
            JournalEntryDTO(
                journal_number=entry.journal_number,
                entry_date=entry.entry_date,
                description=entry.description,
                lines=lines,
                source_type=entry.source_type,
                reference_number=entry.reference_number,
                currency=entry.currency,
                idempotency_key=entry.idempotency_key,
            )
        )
    result = await provider.import_entries(society_id, dtos, dry_run=payload.dry_run)
    return ProviderResultResponse(
        success=result.success,
        message=result.message,
        record_id=result.record_id,
        journal_number=result.journal_number,
        details=result.details,
        errors=result.errors,
    )


@router.get("/export")
async def export_journal_entries(
    society_id: UUID,
    format: str = Query("json", pattern="^(json|csv)$"),
    period_id: UUID | None = Query(None, description="Optional period ID"),
    db: AsyncSession = Depends(get_db_session),
    _: UUID = Depends(resolve_society_context),
    __: User = Depends(require_permission("finance.read")),
) -> Any:
    """Export posted journal entries in JSON or CSV format."""
    provider = ImportExportProvider(db)
    if format == "csv":
        csv_data = await provider.export_to_csv(society_id, period_id)
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="journals_{society_id}.csv"'},
        )
    entries = await provider.export_entries(society_id, period_id)
    return {"society_id": str(society_id), "count": len(entries), "entries": entries}
