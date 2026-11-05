"""Accounting Provider Factory."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.finance.infrastructure.repositories import AccountingConfigRepository
from apps.api.src.finance.providers.base import AccountingProvider
from apps.api.src.finance.providers.import_export import ImportExportProvider
from apps.api.src.finance.providers.native import NativeAccountingProvider
from apps.api.src.finance.providers.tally import TallyProvider


async def get_accounting_provider(session: AsyncSession, society_id: UUID) -> AccountingProvider:
    """Resolve and instantiate the appropriate AccountingProvider for a society."""
    config_repo = AccountingConfigRepository(session)
    config = await config_repo.get_by_society_id(society_id)

    if not config or config.accounting_mode == "NATIVE":
        return NativeAccountingProvider(session)

    if config.accounting_mode == "TALLY":
        return TallyProvider(session)

    if config.accounting_mode == "IMPORT_EXPORT":
        return ImportExportProvider(session)

    if config.accounting_mode == "HYBRID":
        # In hybrid mode, core postings go through native with Tally sync awareness
        return NativeAccountingProvider(session)

    return NativeAccountingProvider(session)
