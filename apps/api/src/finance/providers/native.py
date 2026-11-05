"""Native Accounting Provider implementation."""

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.database.models.finance import (
    JournalEntry,
    JournalEntryLine,
)
from apps.api.src.finance.application.journal_service import JournalService
from apps.api.src.finance.application.period_service import PeriodService
from apps.api.src.finance.domain.exceptions import (
    ClosedPeriodPostingException,
    InactiveAccountPostingException,
    UnbalancedJournalException,
)
from apps.api.src.finance.domain.models import (
    JournalStatus,
    NormalBalance,
    quantize_amount,
)
from apps.api.src.finance.infrastructure.repositories import (
    AccountRepository,
    JournalRepository,
    PeriodRepository,
)
from apps.api.src.finance.providers.base import (
    AccountingProvider,
    JournalEntryDTO,
    ProviderResult,
)


class NativeAccountingProvider(AccountingProvider):
    """Direct database-backed accounting engine adhering to double-entry rules."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.journal_service = JournalService(session)
        self.journal_repo = JournalRepository(session)
        self.account_repo = AccountRepository(session)
        self.period_repo = PeriodRepository(session)
        self.period_service = PeriodService(session)

    async def create_entry(self, society_id: UUID, entry: JournalEntryDTO) -> ProviderResult:
        """Create a draft journal entry from a DTO."""
        try:
            # 1. Resolve financial period for entry_date
            period = await self.period_repo.get_period_for_date(society_id, entry.entry_date)
            if not period:
                return ProviderResult(
                    success=False,
                    message=f"No financial period found covering date {entry.entry_date}.",
                    errors=["PERIOD_NOT_FOUND"],
                )
            if period.status != "OPEN":
                return ProviderResult(
                    success=False,
                    message=f"Financial period {period.name} is CLOSED.",
                    errors=["PERIOD_CLOSED"],
                )

            # 2. Resolve account codes to account IDs
            lines_data: list[dict[str, Any]] = []
            for line in entry.lines:
                acc = await self.account_repo.get_by_code(society_id, line.account_code)
                if not acc:
                    return ProviderResult(
                        success=False,
                        message=f"Account with code '{line.account_code}' does not exist in society.",
                        errors=[f"ACCOUNT_NOT_FOUND: {line.account_code}"],
                    )
                if not acc.is_active:
                    return ProviderResult(
                        success=False,
                        message=f"Account '{line.account_code}' is inactive.",
                        errors=[f"ACCOUNT_INACTIVE: {line.account_code}"],
                    )
                lines_data.append(
                    {
                        "account_id": acc.id,
                        "debit_amount": line.debit_amount,
                        "credit_amount": line.credit_amount,
                        "description": line.description or entry.description,
                    }
                )

            journal = await self.journal_service.create_draft_journal(
                society_id=society_id,
                financial_period_id=period.id,
                entry_date=entry.entry_date,
                description=entry.description,
                lines_data=lines_data,
                source_type=entry.source_type,
                source_record_id=entry.source_record_id,
                reference_number=entry.reference_number,
                currency=entry.currency,
                idempotency_key=entry.idempotency_key,
            )

            return ProviderResult(
                success=True,
                message="Draft journal entry created successfully.",
                record_id=str(journal.id),
                journal_number=journal.journal_number,
                details={"status": journal.status, "period_id": str(period.id)},
            )
        except (
            UnbalancedJournalException,
            InactiveAccountPostingException,
            ClosedPeriodPostingException,
        ) as e:
            return ProviderResult(
                success=False,
                message=str(e),
                errors=[e.__class__.__name__],
            )
        except Exception as e:
            return ProviderResult(
                success=False,
                message=f"Unexpected error creating journal entry: {e}",
                errors=[str(e)],
            )

    async def post_entry(
        self, society_id: UUID, journal_id: UUID, posted_by: UUID | None = None
    ) -> ProviderResult:
        """Post a journal entry to the permanent ledger."""
        try:
            journal = await self.journal_service.post_journal(
                society_id=society_id,
                journal_id=journal_id,
                posted_by=posted_by,
            )
            return ProviderResult(
                success=True,
                message="Journal entry posted successfully.",
                record_id=str(journal.id),
                journal_number=journal.journal_number,
                details={"status": journal.status, "posted_at": str(journal.posted_at)},
            )
        except Exception as e:
            return ProviderResult(
                success=False,
                message=str(e),
                errors=[e.__class__.__name__, str(e)],
            )

    async def reverse_entry(
        self, society_id: UUID, journal_id: UUID, reason: str, reversed_by: UUID | None = None
    ) -> ProviderResult:
        """Create and post a balanced reversal entry."""
        try:
            reversal = await self.journal_service.reverse_journal(
                society_id=society_id,
                journal_id=journal_id,
                reason=reason,
                reversed_by=reversed_by,
            )
            return ProviderResult(
                success=True,
                message="Reversal journal entry created and posted successfully.",
                record_id=str(reversal.id),
                journal_number=reversal.journal_number,
                details={"status": reversal.status, "reversed_entry_id": str(journal_id)},
            )
        except Exception as e:
            return ProviderResult(
                success=False,
                message=str(e),
                errors=[e.__class__.__name__, str(e)],
            )

    async def get_balance(self, society_id: UUID, account_code: str) -> Decimal:
        """Retrieve the closing balance for an account code based on its normal balance."""
        acc = await self.account_repo.get_by_code(society_id, account_code)
        if not acc:
            return Decimal("0.0000")

        stmt = (
            select(JournalEntryLine)
            .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
            .where(
                JournalEntryLine.society_id == society_id,
                JournalEntryLine.account_id == acc.id,
                JournalEntry.status == JournalStatus.POSTED.value,
            )
        )
        result = await self.session.execute(stmt)
        lines = result.scalars().all()

        total_debit = quantize_amount(
            sum((Decimal(str(line.debit_amount)) for line in lines), Decimal("0.0000"))
        )
        total_credit = quantize_amount(
            sum((Decimal(str(line.credit_amount)) for line in lines), Decimal("0.0000"))
        )

        if acc.normal_balance == NormalBalance.DEBIT.value:
            return quantize_amount(total_debit - total_credit)
        else:
            return quantize_amount(total_credit - total_debit)

    async def export_entries(self, society_id: UUID, period_id: UUID | None = None) -> list[dict[str, Any]]:
        """Export posted ledger entries for data interchange."""
        stmt = (
            select(JournalEntry)
            .options(
                selectinload(JournalEntry.lines).selectinload(JournalEntryLine.account),
                selectinload(JournalEntry.period),
            )
            .where(
                JournalEntry.society_id == society_id,
                JournalEntry.status == JournalStatus.POSTED.value,
            )
        )
        if period_id:
            stmt = stmt.where(JournalEntry.financial_period_id == period_id)

        stmt = stmt.order_by(JournalEntry.entry_date.asc(), JournalEntry.journal_number.asc())
        result = await self.session.execute(stmt)
        entries = result.scalars().all()

        exported: list[dict[str, Any]] = []
        for e in entries:
            entry_dict = {
                "journal_number": e.journal_number,
                "entry_date": e.entry_date.isoformat(),
                "description": e.description,
                "source_type": e.source_type,
                "reference_number": e.reference_number,
                "total_debit": str(e.total_debit),
                "total_credit": str(e.total_credit),
                "currency": e.currency,
                "lines": [
                    {
                        "account_code": line.account.account_code,
                        "account_name": line.account.account_name,
                        "debit_amount": str(line.debit_amount),
                        "credit_amount": str(line.credit_amount),
                        "description": line.description,
                    }
                    for line in e.lines
                ],
            }
            exported.append(entry_dict)

        return exported

    async def import_entries(
        self, society_id: UUID, entries: list[JournalEntryDTO], dry_run: bool = True
    ) -> ProviderResult:
        """Validate and optionally import external journal entries."""
        errors: list[str] = []
        validated_entries = 0

        for idx, entry in enumerate(entries):
            # Check debit == credit
            total_deb = quantize_amount(sum((line.debit_amount for line in entry.lines), Decimal("0.0000")))
            total_crd = quantize_amount(sum((line.credit_amount for line in entry.lines), Decimal("0.0000")))
            if total_deb != total_crd:
                errors.append(
                    f"Entry #{idx + 1} ({entry.journal_number or 'unnamed'}): Unbalanced debits={total_deb} != credits={total_crd}"
                )
                continue

            if len(entry.lines) < 2:
                errors.append(f"Entry #{idx + 1}: Must contain at least two lines.")
                continue

            # Verify period
            period = await self.period_repo.get_period_for_date(society_id, entry.entry_date)
            if not period or period.status != "OPEN":
                errors.append(f"Entry #{idx + 1}: No OPEN financial period for date {entry.entry_date}.")
                continue

            # Verify accounts
            missing_accounts = []
            for line in entry.lines:
                acc = await self.account_repo.get_by_code(society_id, line.account_code)
                if not acc or not acc.is_active:
                    missing_accounts.append(line.account_code)

            if missing_accounts:
                errors.append(f"Entry #{idx + 1}: Inactive or missing accounts: {missing_accounts}")
                continue

            validated_entries += 1

        if errors:
            return ProviderResult(
                success=False,
                message=f"Validation failed with {len(errors)} error(s).",
                details={"validated_count": validated_entries, "total_count": len(entries)},
                errors=errors,
            )

        if dry_run:
            return ProviderResult(
                success=True,
                message=f"Dry run successful. {validated_entries} entries validated.",
                details={"validated_count": validated_entries, "dry_run": True},
            )

        # Execute actual import
        imported_ids = []
        for entry in entries:
            res = await self.create_entry(society_id, entry)
            if res.success and res.record_id:
                # Also post it
                post_res = await self.post_entry(society_id, UUID(res.record_id))
                if post_res.success:
                    imported_ids.append(res.record_id)
                else:
                    errors.append(f"Failed to post entry {res.journal_number}: {post_res.message}")
            else:
                errors.append(f"Failed to create entry: {res.message}")

        return ProviderResult(
            success=len(errors) == 0,
            message=f"Imported {len(imported_ids)} of {len(entries)} entries.",
            details={"imported_count": len(imported_ids), "imported_ids": imported_ids},
            errors=errors,
        )

    async def health_check(self, society_id: UUID) -> bool:
        """Verify native database accounting engine availability."""
        try:
            # Simple query to check database responsiveness
            await self.account_repo.list_accounts(society_id)
            return True
        except Exception:
            return False
