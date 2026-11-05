"""Data Access Repositories for Financial Entities."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.database.models.finance import (
    Account,
    Expense,
    FinancialPeriod,
    FinancialReport,
    JournalEntry,
    JournalEntryLine,
    SocietyAccountingConfig,
)
from apps.api.src.finance.domain.models import (
    JournalStatus,
    PeriodStatus,
    quantize_amount,
)


class PeriodRepository:
    """Repository for managing financial reporting periods."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_period(
        self,
        society_id: UUID,
        name: str,
        fiscal_year: str,
        start_date: date,
        end_date: date,
        created_by: UUID | None = None,
        currency: str = "INR",
    ) -> FinancialPeriod:
        period = FinancialPeriod(
            id=uuid.uuid4(),
            society_id=society_id,
            name=name,
            fiscal_year=fiscal_year,
            start_date=start_date,
            end_date=end_date,
            status=PeriodStatus.OPEN.value,
            currency=currency,
            created_by=created_by,
        )
        self.session.add(period)
        await self.session.flush()
        return period

    async def get_by_id(self, period_id: UUID, society_id: UUID | None = None) -> FinancialPeriod | None:
        query = select(FinancialPeriod).where(FinancialPeriod.id == period_id)
        if society_id:
            query = query.where(FinancialPeriod.society_id == society_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_open_period_for_date(self, society_id: UUID, target_date: date) -> FinancialPeriod | None:
        query = select(FinancialPeriod).where(
            FinancialPeriod.society_id == society_id,
            FinancialPeriod.status == PeriodStatus.OPEN.value,
            FinancialPeriod.start_date <= target_date,
            FinancialPeriod.end_date >= target_date,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_period_for_date(self, society_id: UUID, target_date: date) -> FinancialPeriod | None:
        query = select(FinancialPeriod).where(
            FinancialPeriod.society_id == society_id,
            FinancialPeriod.start_date <= target_date,
            FinancialPeriod.end_date >= target_date,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_periods(self, society_id: UUID) -> list[FinancialPeriod]:
        result = await self.session.execute(
            select(FinancialPeriod)
            .where(FinancialPeriod.society_id == society_id)
            .order_by(FinancialPeriod.start_date.desc())
        )
        return list(result.scalars().all())

    async def close_period(self, period_id: UUID, closed_by: UUID) -> None:
        await self.session.execute(
            update(FinancialPeriod)
            .where(FinancialPeriod.id == period_id)
            .values(
                status=PeriodStatus.CLOSED.value,
                closed_at=datetime.now(UTC),
                closed_by=closed_by,
            )
        )

    async def reopen_period(self, period_id: UUID) -> None:
        await self.session.execute(
            update(FinancialPeriod)
            .where(FinancialPeriod.id == period_id)
            .values(
                status=PeriodStatus.OPEN.value,
                closed_at=None,
                closed_by=None,
            )
        )


class AccountRepository:
    """Repository for Chart of Accounts management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_account(
        self,
        society_id: UUID,
        account_code: str,
        account_name: str,
        account_type: str,
        normal_balance: str,
        sub_type: str | None = None,
        parent_account_id: UUID | None = None,
        currency: str = "INR",
        is_system_account: bool = False,
    ) -> Account:
        account = Account(
            id=uuid.uuid4(),
            society_id=society_id,
            account_code=account_code.strip().upper(),
            account_name=account_name.strip(),
            account_type=account_type,
            sub_type=sub_type,
            parent_account_id=parent_account_id,
            normal_balance=normal_balance,
            currency=currency,
            is_active=True,
            is_system_account=is_system_account,
        )
        self.session.add(account)
        await self.session.flush()
        return account

    async def get_by_id(self, account_id: UUID, society_id: UUID | None = None) -> Account | None:
        query = select(Account).where(Account.id == account_id, Account.archived_at.is_(None))
        if society_id:
            query = query.where(Account.society_id == society_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_code(self, society_id: UUID, account_code: str) -> Account | None:
        query = select(Account).where(
            Account.society_id == society_id,
            Account.account_code == account_code.strip().upper(),
            Account.archived_at.is_(None),
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_accounts(
        self,
        society_id: UUID,
        account_type: str | None = None,
        active_only: bool = False,
        include_inactive: bool | None = None,
    ) -> list[Account]:
        query = select(Account).where(
            Account.society_id == society_id,
            Account.archived_at.is_(None),
        )
        if account_type:
            query = query.where(Account.account_type == account_type)
        if active_only or (include_inactive is False):
            query = query.where(Account.is_active.is_(True))
        query = query.order_by(Account.account_code.asc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def deactivate_account(self, account_id: UUID, society_id: UUID) -> None:
        await self.session.execute(
            update(Account)
            .where(Account.id == account_id, Account.society_id == society_id)
            .values(is_active=False)
        )


class JournalRepository:
    """Repository for Journal Entries and Lines."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def generate_journal_number(self, society_id: UUID, prefix: str = "JV") -> str:
        """Deterministically sequence journal numbers per society."""
        count_res = await self.session.execute(
            select(func.count(JournalEntry.id)).where(JournalEntry.society_id == society_id)
        )
        next_seq = (count_res.scalar() or 0) + 1
        return f"{prefix}-{next_seq:06d}"

    async def create_journal(
        self,
        society_id: UUID,
        financial_period_id: UUID,
        journal_number: str,
        entry_date: date,
        description: str,
        lines_data: list[dict[str, Any]],
        source_type: str = "MANUAL",
        source_record_id: str | None = None,
        reference_number: str | None = None,
        currency: str = "INR",
        idempotency_key: str | None = None,
        created_by: UUID | None = None,
    ) -> JournalEntry:
        # Calculate totals
        total_debit = sum(quantize_amount(line["debit_amount"]) for line in lines_data)
        total_credit = sum(quantize_amount(line["credit_amount"]) for line in lines_data)

        journal = JournalEntry(
            id=uuid.uuid4(),
            society_id=society_id,
            financial_period_id=financial_period_id,
            journal_number=journal_number,
            entry_date=entry_date,
            description=description,
            status=JournalStatus.DRAFT.value,
            source_type=source_type,
            source_record_id=source_record_id,
            reference_number=reference_number,
            currency=currency,
            total_debit=total_debit,
            total_credit=total_credit,
            idempotency_key=idempotency_key,
            created_by=created_by,
        )
        self.session.add(journal)
        await self.session.flush()

        # Add lines
        for idx, line in enumerate(lines_data, start=1):
            jl = JournalEntryLine(
                id=uuid.uuid4(),
                journal_entry_id=journal.id,
                society_id=society_id,
                account_id=line["account_id"],
                line_number=idx,
                description=line.get("description"),
                debit_amount=quantize_amount(line["debit_amount"]),
                credit_amount=quantize_amount(line["credit_amount"]),
            )
            self.session.add(jl)

        await self.session.flush()
        loaded = await self.get_by_id(journal.id, society_id)
        return loaded or journal

    async def get_by_id(self, journal_id: UUID, society_id: UUID | None = None) -> JournalEntry | None:
        query = (
            select(JournalEntry)
            .options(selectinload(JournalEntry.lines).selectinload(JournalEntryLine.account))
            .where(JournalEntry.id == journal_id)
        )
        if society_id:
            query = query.where(JournalEntry.society_id == society_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, society_id: UUID, idempotency_key: str) -> JournalEntry | None:
        query = (
            select(JournalEntry)
            .options(selectinload(JournalEntry.lines))
            .where(
                JournalEntry.society_id == society_id,
                JournalEntry.idempotency_key == idempotency_key,
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_journals(
        self,
        society_id: UUID,
        status: str | None = None,
        period_id: UUID | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[JournalEntry]:
        query = (
            select(JournalEntry)
            .options(selectinload(JournalEntry.lines))
            .where(JournalEntry.society_id == society_id)
        )
        if status:
            query = query.where(JournalEntry.status == status)
        if period_id:
            query = query.where(JournalEntry.financial_period_id == period_id)
        if start_date:
            query = query.where(JournalEntry.entry_date >= start_date)
        if end_date:
            query = query.where(JournalEntry.entry_date <= end_date)
        query = (
            query.order_by(JournalEntry.entry_date.desc(), JournalEntry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def post_journal(self, journal_id: UUID, posted_by: UUID | None) -> None:
        await self.session.execute(
            update(JournalEntry)
            .where(JournalEntry.id == journal_id)
            .values(
                status=JournalStatus.POSTED.value,
                posted_by=posted_by,
                posted_at=datetime.now(UTC),
            )
        )

    async def mark_reversed(self, original_id: UUID, reversal_id: UUID, reason: str | None = None) -> None:
        await self.session.execute(
            update(JournalEntry)
            .where(JournalEntry.id == original_id)
            .values(
                status=JournalStatus.REVERSED.value,
                reversed_entry_id=reversal_id,
                reversal_reason=reason,
            )
        )


class ExpenseRepository:
    """Repository for managing society expenses."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def generate_expense_number(self, society_id: UUID, prefix: str = "EXP") -> str:
        count_res = await self.session.execute(
            select(func.count(Expense.id)).where(Expense.society_id == society_id)
        )
        next_seq = (count_res.scalar() or 0) + 1
        return f"{prefix}-{next_seq:06d}"

    async def create_expense(
        self,
        society_id: UUID,
        financial_period_id: UUID,
        expense_number: str,
        expense_date: date,
        category_account_id: UUID,
        paid_from_account_id: UUID,
        description: str,
        amount: Decimal,
        currency: str = "INR",
        reference_number: str | None = None,
        vendor_name: str | None = None,
        created_by: UUID | None = None,
    ) -> Expense:
        expense = Expense(
            id=uuid.uuid4(),
            society_id=society_id,
            financial_period_id=financial_period_id,
            expense_number=expense_number,
            expense_date=expense_date,
            category_account_id=category_account_id,
            paid_from_account_id=paid_from_account_id,
            description=description,
            amount=quantize_amount(amount),
            currency=currency,
            status="DRAFT",
            reference_number=reference_number,
            vendor_name=vendor_name,
            created_by=created_by,
        )
        self.session.add(expense)
        await self.session.flush()
        return expense

    async def get_by_id(self, expense_id: UUID, society_id: UUID | None = None) -> Expense | None:
        query = select(Expense).where(Expense.id == expense_id)
        if society_id:
            query = query.where(Expense.society_id == society_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_expenses(
        self,
        society_id: UUID,
        status: str | None = None,
        period_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Expense]:
        query = select(Expense).where(Expense.society_id == society_id)
        if status:
            query = query.where(Expense.status == status)
        if period_id:
            query = query.where(Expense.financial_period_id == period_id)
        query = (
            query.order_by(Expense.expense_date.desc(), Expense.created_at.desc()).limit(limit).offset(offset)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def approve_expense(self, expense_id: UUID, approved_by: UUID) -> None:
        await self.session.execute(
            update(Expense)
            .where(Expense.id == expense_id)
            .values(
                status="APPROVED",
                approved_by=approved_by,
                approved_at=datetime.now(UTC),
            )
        )

    async def mark_posted(self, expense_id: UUID, journal_id: UUID) -> None:
        await self.session.execute(
            update(Expense)
            .where(Expense.id == expense_id)
            .values(
                status="POSTED",
                journal_entry_id=journal_id,
            )
        )


class FinancialReportRepository:
    """Repository for managing versioned financial reports."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save_report(
        self,
        society_id: UUID,
        financial_period_id: UUID,
        report_type: str,
        name: str,
        report_data: dict[str, Any],
        generated_by: UUID | None = None,
        status: str = "GENERATED",
    ) -> FinancialReport:
        # Determine next version
        max_v_res = await self.session.execute(
            select(func.max(FinancialReport.version)).where(
                FinancialReport.society_id == society_id,
                FinancialReport.report_type == report_type,
                FinancialReport.financial_period_id == financial_period_id,
            )
        )
        current_max = max_v_res.scalar() or 0
        new_version = current_max + 1

        report = FinancialReport(
            id=uuid.uuid4(),
            society_id=society_id,
            financial_period_id=financial_period_id,
            report_type=report_type,
            name=name,
            version=new_version,
            status=status,
            report_data=report_data,
            generated_at=datetime.now(UTC),
            generated_by=generated_by,
        )
        self.session.add(report)
        await self.session.flush()
        return report

    async def get_by_id(self, report_id: UUID, society_id: UUID | None = None) -> FinancialReport | None:
        query = select(FinancialReport).where(FinancialReport.id == report_id)
        if society_id:
            query = query.where(FinancialReport.society_id == society_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_latest_report(
        self, society_id: UUID, report_type: str, financial_period_id: UUID
    ) -> FinancialReport | None:
        query = (
            select(FinancialReport)
            .where(
                FinancialReport.society_id == society_id,
                FinancialReport.report_type == report_type,
                FinancialReport.financial_period_id == financial_period_id,
            )
            .order_by(FinancialReport.version.desc())
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_reports(
        self,
        society_id: UUID,
        report_type: str | None = None,
        period_id: UUID | None = None,
    ) -> list[FinancialReport]:
        query = select(FinancialReport).where(FinancialReport.society_id == society_id)
        if report_type:
            query = query.where(FinancialReport.report_type == report_type)
        if period_id:
            query = query.where(FinancialReport.financial_period_id == period_id)
        query = query.order_by(FinancialReport.generated_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_status(self, report_id: UUID, status: str, user_id: UUID) -> None:
        vals: dict[str, Any] = {"status": status}
        if status == "APPROVED":
            vals["approved_at"] = datetime.now(UTC)
            vals["approved_by"] = user_id
        elif status == "PUBLISHED":
            vals["published_at"] = datetime.now(UTC)
            vals["published_by"] = user_id

        await self.session.execute(
            update(FinancialReport).where(FinancialReport.id == report_id).values(**vals)
        )


class AccountingConfigRepository:
    """Repository for per-society accounting mode and external provider metadata."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_society_id(self, society_id: UUID) -> SocietyAccountingConfig | None:
        res = await self.session.execute(
            select(SocietyAccountingConfig).where(SocietyAccountingConfig.society_id == society_id)
        )
        return res.scalar_one_or_none()

    async def create_config(
        self, society_id: UUID, accounting_mode: str = "NATIVE", authoritative_source: str = "INTERNAL"
    ) -> SocietyAccountingConfig:
        config = SocietyAccountingConfig(
            id=uuid.uuid4(),
            society_id=society_id,
            accounting_mode=accounting_mode,
            authoritative_source=authoritative_source,
            default_currency="INR",
        )
        self.session.add(config)
        await self.session.flush()
        return config

    async def get_or_create(self, society_id: UUID) -> SocietyAccountingConfig:
        config = await self.get_by_society_id(society_id)
        if not config:
            config = await self.create_config(society_id)
        return config

    async def update_config(
        self,
        society_id: UUID,
        accounting_mode: str | None = None,
        authoritative_source: str | None = None,
        tally_company_name: str | None = None,
        tally_guid: str | None = None,
        sync_metadata: dict[str, Any] | None = None,
    ) -> SocietyAccountingConfig:
        config = await self.get_or_create(society_id)
        if accounting_mode is not None:
            config.accounting_mode = accounting_mode
        if authoritative_source is not None:
            config.authoritative_source = authoritative_source
        if tally_company_name is not None:
            config.tally_company_name = tally_company_name
        if tally_guid is not None:
            config.tally_guid = tally_guid
        if sync_metadata is not None:
            config.sync_metadata = sync_metadata
        await self.session.flush()
        return config
