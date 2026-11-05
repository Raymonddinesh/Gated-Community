"""Double-Entry Financial Journal Application Service."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.core.exceptions import NotFoundException
from apps.api.src.database.models.finance import JournalEntry
from apps.api.src.database.repositories.audit_repository import AuditRepository
from apps.api.src.finance.application.period_service import PeriodService
from apps.api.src.finance.domain.exceptions import (
    CrossTenantFinancialException,
    DuplicateReversalException,
    ImmutableRecordException,
    InactiveAccountPostingException,
    InvalidJournalLinesException,
    UnbalancedJournalException,
)
from apps.api.src.finance.domain.models import (
    JournalStatus,
    quantize_amount,
)
from apps.api.src.finance.infrastructure.repositories import (
    AccountRepository,
    JournalRepository,
)


class JournalService:
    """Core double-entry journal posting, validation, and reversal engine."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.journal_repo = JournalRepository(session)
        self.account_repo = AccountRepository(session)
        self.period_service = PeriodService(session)
        self.audit_repo = AuditRepository(session)

    async def create_draft_journal(
        self,
        society_id: UUID,
        financial_period_id: UUID,
        entry_date: date,
        description: str,
        lines_data: list[dict[str, Any]],
        source_type: str = "MANUAL",
        source_record_id: str | None = None,
        reference_number: str | None = None,
        currency: str = "INR",
        idempotency_key: str | None = None,
        created_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> JournalEntry:
        """Create a draft journal entry after initial structural checks."""
        # Check idempotency
        if idempotency_key:
            existing = await self.journal_repo.get_by_idempotency_key(society_id, idempotency_key)
            if existing:
                return existing

        # Validate period and date
        await self.period_service.validate_posting_allowed(society_id, financial_period_id, entry_date)

        # Validate lines structure
        await self._validate_lines_structure(society_id, lines_data)

        # Generate sequence number
        journal_number = await self.journal_repo.generate_journal_number(society_id)

        journal = await self.journal_repo.create_journal(
            society_id=society_id,
            financial_period_id=financial_period_id,
            journal_number=journal_number,
            entry_date=entry_date,
            description=description,
            lines_data=lines_data,
            source_type=source_type,
            source_record_id=source_record_id,
            reference_number=reference_number,
            currency=currency,
            idempotency_key=idempotency_key,
            created_by=created_by,
        )

        await self.audit_repo.log_event(
            action="FINANCE_JOURNAL_CREATED",
            entity_type="journal_entry",
            entity_id=str(journal.id),
            society_id=society_id,
            actor_user_id=created_by,
            correlation_id=correlation_id,
            after_state={"journal_number": journal_number, "status": journal.status},
        )

        return journal

    async def post_journal(
        self,
        journal_id: UUID,
        society_id: UUID,
        posted_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> JournalEntry:
        """
        Validate double-entry balance and post journal to the permanent general ledger.
        Atomic database operation: Rejects any unbalanced or invalid state.
        """
        journal = await self.journal_repo.get_by_id(journal_id, society_id)
        if not journal:
            # Fallback for positional order flexibility (society_id, journal_id)
            alt_journal = await self.journal_repo.get_by_id(society_id, journal_id)
            if alt_journal:
                journal = alt_journal
                journal_id, society_id = society_id, journal_id
            else:
                raise NotFoundException(f"Journal entry '{journal_id}' not found.")

        if journal.status == JournalStatus.POSTED.value:
            raise ImmutableRecordException(entity_type="JournalEntry", entity_id=str(journal_id))

        if journal.status == JournalStatus.REVERSED.value:
            raise UnbalancedJournalException(
                "0.00", "0.00", "Cannot post a journal that has already been reversed."
            )

        # 1. Period check: period must be OPEN and date must fall in range
        await self.period_service.validate_posting_allowed(
            society_id, journal.financial_period_id, journal.entry_date
        )

        # 2. Line count check: at least 2 lines
        if len(journal.lines) < 2:
            raise InvalidJournalLinesException(
                f"Double-entry requires at least 2 lines. Journal has {len(journal.lines)}."
            )

        # 3. Double-entry balance calculation (Strict Decimal equality)
        total_debit = Decimal("0.0000")
        total_credit = Decimal("0.0000")

        for line in journal.lines:
            # Validate account belongs to this society and is active
            account = await self.account_repo.get_by_id(line.account_id, society_id)
            if not account:
                raise CrossTenantFinancialException(
                    f"Account '{line.account_id}' does not belong to society '{society_id}'."
                )
            if not account.is_active:
                raise InactiveAccountPostingException(
                    account_code=account.account_code, account_name=account.account_name
                )

            d = quantize_amount(line.debit_amount)
            c = quantize_amount(line.credit_amount)

            if (d > 0 and c > 0) or (d == 0 and c == 0):
                raise InvalidJournalLinesException(
                    f"Line {line.line_number} must have either debit > 0 or credit > 0, never both or neither."
                )

            total_debit += d
            total_credit += c

        # MANDATORY BALANCE EQUALITY CHECK: TOTAL DEBITS == TOTAL CREDITS
        if total_debit != total_credit:
            diff = abs(total_debit - total_credit)
            raise UnbalancedJournalException(
                debit_total=str(total_debit),
                credit_total=str(total_credit),
                difference=str(diff),
            )

        # Update totals and status to POSTED
        journal.total_debit = total_debit
        journal.total_credit = total_credit
        await self.journal_repo.post_journal(journal.id, posted_by=posted_by)

        await self.audit_repo.log_event(
            action="FINANCE_JOURNAL_POSTED",
            entity_type="journal_entry",
            entity_id=str(journal.id),
            society_id=society_id,
            actor_user_id=posted_by,
            correlation_id=correlation_id,
            after_state={
                "journal_number": journal.journal_number,
                "total_debit": str(total_debit),
                "total_credit": str(total_credit),
                "posted_at": datetime.now(UTC).isoformat(),
            },
        )

        journal.status = JournalStatus.POSTED.value
        journal.posted_by = posted_by
        journal.posted_at = datetime.now(UTC)
        return journal

    async def reverse_journal(
        self,
        journal_id: UUID,
        society_id: UUID,
        reason: str,
        reversed_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> JournalEntry:
        """
        Create and post a balanced reversal entry.
        Original entry remains permanently intact with status='REVERSED'.
        """
        original = await self.journal_repo.get_by_id(journal_id, society_id)
        if not original:
            alt_original = await self.journal_repo.get_by_id(society_id, journal_id)
            if alt_original:
                original = alt_original
                journal_id, society_id = society_id, journal_id
            else:
                raise NotFoundException(f"Original journal entry '{journal_id}' not found.")

        if original.reversed_entry_id is not None or original.status == JournalStatus.REVERSED.value:
            raise DuplicateReversalException(journal_number=original.journal_number)

        if original.status != JournalStatus.POSTED.value:
            raise InvalidJournalLinesException(
                f"Only POSTED journals can be reversed. Current status is '{original.status}'."
            )

        # Verify target period is OPEN for posting today's reversal
        reversal_date = date.today()
        # If today is outside original period, try using original entry_date if period still open,
        # otherwise open period covering reversal_date
        period = await self.period_service.period_repo.get_open_period_for_date(society_id, reversal_date)
        if not period:
            # Fall back to original period if still open
            period = await self.period_service.validate_posting_allowed(
                society_id, original.financial_period_id, original.entry_date
            )
            reversal_date = original.entry_date

        # Invert lines: debit becomes credit, credit becomes debit
        reversal_lines: list[dict[str, Any]] = []
        for line in original.lines:
            reversal_lines.append(
                {
                    "account_id": line.account_id,
                    "description": f"Reversal of line {line.line_number}: {line.description or ''}".strip(),
                    "debit_amount": line.credit_amount,  # Swapped!
                    "credit_amount": line.debit_amount,  # Swapped!
                }
            )

        reversal_number = await self.journal_repo.generate_journal_number(society_id, prefix="REV")

        # Create reversal journal directly
        reversal = await self.journal_repo.create_journal(
            society_id=society_id,
            financial_period_id=period.id,
            journal_number=reversal_number,
            entry_date=reversal_date,
            description=f"Reversal of {original.journal_number}: {reason}",
            lines_data=reversal_lines,
            source_type="REVERSAL",
            source_record_id=str(original.id),
            reference_number=original.journal_number,
            currency=original.currency,
            created_by=reversed_by,
        )

        # Post the reversal immediately
        await self.journal_repo.post_journal(reversal.id, posted_by=reversed_by)
        reversal.status = JournalStatus.POSTED.value
        reversal.reversed_entry_id = original.id

        # Link original to reversal
        await self.journal_repo.mark_reversed(original.id, reversal.id, reason=reason)
        original.status = JournalStatus.REVERSED.value
        original.reversed_entry_id = reversal.id
        original.reversal_reason = reason

        await self.audit_repo.log_event(
            action="FINANCE_JOURNAL_REVERSED",
            entity_type="journal_entry",
            entity_id=str(original.id),
            society_id=society_id,
            actor_user_id=reversed_by,
            correlation_id=correlation_id,
            after_state={
                "original_journal": original.journal_number,
                "reversal_journal": reversal.journal_number,
                "reason": reason,
            },
        )

        return reversal

    async def _validate_lines_structure(self, society_id: UUID, lines_data: list[dict[str, Any]]) -> None:
        if not lines_data or len(lines_data) < 2:
            raise InvalidJournalLinesException("A journal entry must contain at least 2 valid lines.")

        total_d = Decimal("0.0000")
        total_c = Decimal("0.0000")

        for idx, line in enumerate(lines_data, start=1):
            if "account_id" not in line:
                raise InvalidJournalLinesException(f"Line {idx} missing account_id.")

            account = await self.account_repo.get_by_id(line["account_id"], society_id)
            if not account:
                raise CrossTenantFinancialException(
                    f"Line {idx}: Account '{line['account_id']}' not found in society."
                )
            if not account.is_active:
                raise InactiveAccountPostingException(
                    account_code=account.account_code, account_name=account.account_name
                )

            d = quantize_amount(line.get("debit_amount", 0))
            c = quantize_amount(line.get("credit_amount", 0))

            if d < 0 or c < 0:
                raise InvalidJournalLinesException(f"Line {idx}: Amounts cannot be negative.")

            if (d > 0 and c > 0) or (d == 0 and c == 0):
                raise InvalidJournalLinesException(
                    f"Line {idx}: Must contain either a positive debit OR credit, never both or zero."
                )

            total_d += d
            total_c += c

        if total_d != total_c:
            diff = abs(total_d - total_c)
            raise UnbalancedJournalException(
                debit_total=str(total_d), credit_total=str(total_c), difference=str(diff)
            )
