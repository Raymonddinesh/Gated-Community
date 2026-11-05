"""Import/Export Accounting Provider implementation."""

import csv
import io
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.finance.domain.models import quantize_amount
from apps.api.src.finance.providers.base import (
    AccountingProvider,
    JournalEntryDTO,
    JournalLineDTO,
    ProviderResult,
)
from apps.api.src.finance.providers.native import NativeAccountingProvider


class ImportExportProvider(AccountingProvider):
    """Provider specializing in batch file data validation, import, and export."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.native_provider = NativeAccountingProvider(session)

    async def create_entry(self, society_id: UUID, entry: JournalEntryDTO) -> ProviderResult:
        """Create a journal entry via the underlying engine."""
        return await self.native_provider.create_entry(society_id, entry)

    async def post_entry(
        self, society_id: UUID, journal_id: UUID, posted_by: UUID | None = None
    ) -> ProviderResult:
        """Post a journal entry."""
        return await self.native_provider.post_entry(society_id, journal_id, posted_by)

    async def reverse_entry(
        self, society_id: UUID, journal_id: UUID, reason: str, reversed_by: UUID | None = None
    ) -> ProviderResult:
        """Reverse a journal entry."""
        return await self.native_provider.reverse_entry(society_id, journal_id, reason, reversed_by)

    async def get_balance(self, society_id: UUID, account_code: str) -> Decimal:
        """Get balance for an account."""
        return await self.native_provider.get_balance(society_id, account_code)

    async def export_entries(self, society_id: UUID, period_id: UUID | None = None) -> list[dict[str, Any]]:
        """Export ledger entries."""
        return await self.native_provider.export_entries(society_id, period_id)

    async def export_to_csv(self, society_id: UUID, period_id: UUID | None = None) -> str:
        """Export ledger entries as a standard CSV string."""
        entries = await self.export_entries(society_id, period_id)
        output = io.StringIO()
        fieldnames = [
            "journal_number",
            "entry_date",
            "description",
            "reference_number",
            "account_code",
            "account_name",
            "debit_amount",
            "credit_amount",
            "line_description",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for entry in entries:
            for line in entry.get("lines", []):
                writer.writerow(
                    {
                        "journal_number": entry.get("journal_number"),
                        "entry_date": entry.get("entry_date"),
                        "description": entry.get("description"),
                        "reference_number": entry.get("reference_number", ""),
                        "account_code": line.get("account_code"),
                        "account_name": line.get("account_name"),
                        "debit_amount": line.get("debit_amount"),
                        "credit_amount": line.get("credit_amount"),
                        "line_description": line.get("description", ""),
                    }
                )

        return output.getvalue()

    async def parse_csv_to_entries(self, csv_content: str) -> list[JournalEntryDTO]:
        """Parse standard CSV string into JournalEntryDTO structures grouped by journal_number/ref."""
        reader = csv.DictReader(io.StringIO(csv_content))
        grouped: dict[str, dict[str, Any]] = {}

        for row in reader:
            key = row.get("journal_number") or row.get("reference_number") or row.get("description", "")
            if not key:
                continue

            if key not in grouped:
                entry_date_str = row.get("entry_date", "")
                parsed_date = date.fromisoformat(entry_date_str) if entry_date_str else date.today()
                grouped[key] = {
                    "journal_number": row.get("journal_number"),
                    "entry_date": parsed_date,
                    "description": row.get("description", ""),
                    "reference_number": row.get("reference_number"),
                    "lines": [],
                }

            deb_str = row.get("debit_amount", "0") or "0"
            crd_str = row.get("credit_amount", "0") or "0"

            grouped[key]["lines"].append(
                JournalLineDTO(
                    account_code=row.get("account_code", "").strip(),
                    debit_amount=quantize_amount(Decimal(deb_str)),
                    credit_amount=quantize_amount(Decimal(crd_str)),
                    description=row.get("line_description"),
                )
            )

        result: list[JournalEntryDTO] = []
        for g in grouped.values():
            result.append(
                JournalEntryDTO(
                    journal_number=g["journal_number"],
                    entry_date=g["entry_date"],
                    description=g["description"],
                    reference_number=g["reference_number"],
                    lines=g["lines"],
                    source_type="IMPORT",
                )
            )
        return result

    async def import_entries(
        self, society_id: UUID, entries: list[JournalEntryDTO], dry_run: bool = True
    ) -> ProviderResult:
        """Validate or import batch journal entries."""
        return await self.native_provider.import_entries(society_id, entries, dry_run=dry_run)

    async def health_check(self, society_id: UUID) -> bool:
        """Check availability."""
        return await self.native_provider.health_check(society_id)
