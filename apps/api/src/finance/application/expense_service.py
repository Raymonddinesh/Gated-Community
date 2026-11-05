"""Society Operational Expense Application Service."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.core.exceptions import ConflictException, NotFoundException
from apps.api.src.database.models.finance import Expense
from apps.api.src.database.repositories.audit_repository import AuditRepository
from apps.api.src.finance.application.journal_service import JournalService
from apps.api.src.finance.application.period_service import PeriodService
from apps.api.src.finance.domain.exceptions import CrossTenantFinancialException
from apps.api.src.finance.domain.models import AccountType, quantize_amount
from apps.api.src.finance.infrastructure.repositories import (
    AccountRepository,
    ExpenseRepository,
)


class ExpenseService:
    """Service managing operational expenses and their translation into posted double-entry journals."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.expense_repo = ExpenseRepository(session)
        self.account_repo = AccountRepository(session)
        self.period_service = PeriodService(session)
        self.journal_service = JournalService(session)
        self.audit_repo = AuditRepository(session)

    async def create_expense(
        self,
        society_id: UUID,
        financial_period_id: UUID,
        expense_date: date,
        category_account_id: UUID,
        paid_from_account_id: UUID,
        description: str,
        amount: Decimal | str | float,
        currency: str = "INR",
        reference_number: str | None = None,
        vendor_name: str | None = None,
        created_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> Expense:
        """Create a draft expense with account validation."""
        # Validate period
        await self.period_service.validate_posting_allowed(society_id, financial_period_id, expense_date)

        # Validate accounts
        cat_acc = await self.account_repo.get_by_id(category_account_id, society_id)
        if not cat_acc or cat_acc.account_type != AccountType.EXPENSE.value:
            raise CrossTenantFinancialException(
                "Category account must be a valid, active EXPENSE account belonging to this society."
            )

        pay_acc = await self.account_repo.get_by_id(paid_from_account_id, society_id)
        if not pay_acc or pay_acc.account_type != AccountType.ASSET.value:
            raise CrossTenantFinancialException(
                "Payment source account must be a valid, active ASSET (Bank/Cash) account belonging to this society."
            )

        clean_amount = quantize_amount(amount)
        if clean_amount <= Decimal("0.0000"):
            raise ConflictException("Expense amount must be strictly greater than zero.")

        exp_num = await self.expense_repo.generate_expense_number(society_id)

        expense = await self.expense_repo.create_expense(
            society_id=society_id,
            financial_period_id=financial_period_id,
            expense_number=exp_num,
            expense_date=expense_date,
            category_account_id=category_account_id,
            paid_from_account_id=paid_from_account_id,
            description=description,
            amount=clean_amount,
            currency=currency,
            reference_number=reference_number,
            vendor_name=vendor_name,
            created_by=created_by,
        )

        await self.audit_repo.log_event(
            action="FINANCE_EXPENSE_CREATED",
            entity_type="expense",
            entity_id=str(expense.id),
            society_id=society_id,
            actor_user_id=created_by,
            correlation_id=correlation_id,
            after_state={
                "expense_number": exp_num,
                "amount": str(clean_amount),
                "category": cat_acc.account_name,
            },
        )

        return expense

    async def approve_expense(
        self,
        expense_id: UUID,
        society_id: UUID,
        approved_by: UUID,
        correlation_id: str | None = None,
    ) -> Expense:
        """Approve a draft expense for payment and ledger posting."""
        expense = await self.expense_repo.get_by_id(expense_id, society_id)
        if not expense:
            raise NotFoundException(f"Expense '{expense_id}' not found.")

        if expense.status != "DRAFT":
            raise ConflictException(f"Only DRAFT expenses can be approved (current: {expense.status}).")

        await self.expense_repo.approve_expense(expense.id, approved_by=approved_by)

        await self.audit_repo.log_event(
            action="FINANCE_EXPENSE_APPROVED",
            entity_type="expense",
            entity_id=str(expense.id),
            society_id=society_id,
            actor_user_id=approved_by,
            correlation_id=correlation_id,
            after_state={"status": "APPROVED", "approved_at": datetime.now(UTC).isoformat()},
        )

        expense.status = "APPROVED"
        expense.approved_by = approved_by
        expense.approved_at = datetime.now(UTC)
        return expense

    async def post_expense(
        self,
        expense_id: UUID,
        society_id: UUID,
        posted_by: UUID | None = None,
        correlation_id: str | None = None,
    ) -> Expense:
        """
        Post an approved expense by automatically creating and committing a balanced double-entry journal:
        - Debit: Category Account (EXPENSE)
        - Credit: Paid-From Account (ASSET)
        """
        expense = await self.expense_repo.get_by_id(expense_id, society_id)
        if not expense:
            raise NotFoundException(f"Expense '{expense_id}' not found.")

        if expense.status == "POSTED":
            return expense

        if expense.status != "APPROVED":
            raise ConflictException(f"Expense must be APPROVED prior to posting (current: {expense.status}).")

        # Prepare double-entry lines: Debit Expense, Credit Bank/Cash
        lines_data = [
            {
                "account_id": expense.category_account_id,
                "debit_amount": expense.amount,
                "credit_amount": Decimal("0.0000"),
                "description": f"Expense: {expense.description}",
            },
            {
                "account_id": expense.paid_from_account_id,
                "debit_amount": Decimal("0.0000"),
                "credit_amount": expense.amount,
                "description": f"Payment for: {expense.expense_number}",
            },
        ]

        # Create and post journal atomically
        journal = await self.journal_service.create_draft_journal(
            society_id=society_id,
            financial_period_id=expense.financial_period_id,
            entry_date=expense.expense_date,
            description=f"Operational Expense: {expense.expense_number} - {expense.description}",
            lines_data=lines_data,
            source_type="EXPENSE",
            source_record_id=str(expense.id),
            reference_number=expense.reference_number,
            currency=expense.currency,
            created_by=posted_by,
            correlation_id=correlation_id,
        )

        posted_journal = await self.journal_service.post_journal(
            journal_id=journal.id,
            society_id=society_id,
            posted_by=posted_by,
            correlation_id=correlation_id,
        )

        # Mark expense posted and link journal
        await self.expense_repo.mark_posted(expense.id, posted_journal.id)

        await self.audit_repo.log_event(
            action="FINANCE_EXPENSE_POSTED",
            entity_type="expense",
            entity_id=str(expense.id),
            society_id=society_id,
            actor_user_id=posted_by,
            correlation_id=correlation_id,
            after_state={
                "status": "POSTED",
                "journal_id": str(posted_journal.id),
                "journal_number": posted_journal.journal_number,
            },
        )

        expense.status = "POSTED"
        expense.journal_entry_id = posted_journal.id
        return expense
