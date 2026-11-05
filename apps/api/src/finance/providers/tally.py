"""Tally Accounting Provider adapter stub."""

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.finance.domain.exceptions import ProviderNotConfiguredException
from apps.api.src.finance.infrastructure.repositories import AccountingConfigRepository
from apps.api.src.finance.providers.base import (
    AccountingProvider,
    JournalEntryDTO,
    ProviderResult,
)


class TallyProvider(AccountingProvider):
    """Tally ERP/Prime integration adapter stub with live transport guards.

    Conforms to the AccountingProvider abstraction while maintaining source-of-truth
    rules and not-configured protections.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.config_repo = AccountingConfigRepository(session)

    async def _ensure_configured(self, society_id: UUID) -> Any:
        config = await self.config_repo.get_by_society_id(society_id)
        if not config:
            raise ProviderNotConfiguredException(
                f"No accounting configuration found for society {society_id}."
            )
        if config.accounting_mode not in ("TALLY", "HYBRID"):
            raise ProviderNotConfiguredException(
                f"Society accounting mode is '{config.accounting_mode}', not TALLY or HYBRID."
            )
        if not config.tally_company_name or not config.tally_guid:
            raise ProviderNotConfiguredException(
                "Tally company credentials (company_name, GUID) are not configured."
            )
        return config

    async def create_entry(self, society_id: UUID, entry: JournalEntryDTO) -> ProviderResult:
        """Create journal entry in Tally."""
        try:
            config = await self._ensure_configured(society_id)
            return ProviderResult(
                success=False,
                message=f"Tally endpoint connector for company '{config.tally_company_name}' is not currently reachable.",
                errors=["TALLY_TRANSPORT_UNAVAILABLE"],
                details={"tally_company": config.tally_company_name, "guid": config.tally_guid},
            )
        except ProviderNotConfiguredException as e:
            return ProviderResult(
                success=False,
                message=str(e),
                errors=["TALLY_NOT_CONFIGURED"],
            )

    async def post_entry(
        self, society_id: UUID, journal_id: UUID, posted_by: UUID | None = None
    ) -> ProviderResult:
        """Post journal entry in Tally."""
        try:
            config = await self._ensure_configured(society_id)
            return ProviderResult(
                success=False,
                message=f"Tally synchronization bridge for '{config.tally_company_name}' is offline.",
                errors=["TALLY_TRANSPORT_UNAVAILABLE"],
            )
        except ProviderNotConfiguredException as e:
            return ProviderResult(
                success=False,
                message=str(e),
                errors=["TALLY_NOT_CONFIGURED"],
            )

    async def reverse_entry(
        self, society_id: UUID, journal_id: UUID, reason: str, reversed_by: UUID | None = None
    ) -> ProviderResult:
        """Create reversal voucher in Tally."""
        try:
            config = await self._ensure_configured(society_id)
            return ProviderResult(
                success=False,
                message=f"Tally reversal bridge for '{config.tally_company_name}' is offline.",
                errors=["TALLY_TRANSPORT_UNAVAILABLE"],
            )
        except ProviderNotConfiguredException as e:
            return ProviderResult(
                success=False,
                message=str(e),
                errors=["TALLY_NOT_CONFIGURED"],
            )

    async def get_balance(self, society_id: UUID, account_code: str) -> Decimal:
        """Retrieve ledger balance from Tally."""
        await self._ensure_configured(society_id)
        # In unconfigured or offline state, returns 0.0000
        return Decimal("0.0000")

    async def export_entries(self, society_id: UUID, period_id: UUID | None = None) -> list[dict[str, Any]]:
        """Export ledger entries formatted for Tally XML import."""
        await self._ensure_configured(society_id)
        return []

    async def import_entries(
        self, society_id: UUID, entries: list[JournalEntryDTO], dry_run: bool = True
    ) -> ProviderResult:
        """Validate and ingest entries from Tally."""
        try:
            config = await self._ensure_configured(society_id)
            return ProviderResult(
                success=False,
                message=f"Tally XML sync agent for company '{config.tally_company_name}' is not running.",
                errors=["TALLY_TRANSPORT_UNAVAILABLE"],
            )
        except ProviderNotConfiguredException as e:
            return ProviderResult(
                success=False,
                message=str(e),
                errors=["TALLY_NOT_CONFIGURED"],
            )

    async def health_check(self, society_id: UUID) -> bool:
        """Verify Tally connector availability."""
        try:
            await self._ensure_configured(society_id)
            return False  # Transport stub is offline until remote bridge is connected
        except ProviderNotConfiguredException:
            return False

    async def get_sync_status(self, society_id: UUID) -> dict[str, Any]:
        """Retrieve synchronization metadata."""
        config = await self.config_repo.get_by_society_id(society_id)
        if not config:
            return {
                "configured": False,
                "status": "NOT_CONFIGURED",
                "message": "Accounting configuration missing.",
            }
        sync_meta = config.sync_metadata or {}
        return {
            "configured": config.accounting_mode in ("TALLY", "HYBRID"),
            "accounting_mode": config.accounting_mode,
            "authoritative_source": config.authoritative_source,
            "tally_company_name": config.tally_company_name,
            "last_synced_at": sync_meta.get("last_synced_at"),
            "sync_status": sync_meta.get(
                "sync_status", "OFFLINE" if config.accounting_mode in ("TALLY", "HYBRID") else "NATIVE"
            ),
        }
