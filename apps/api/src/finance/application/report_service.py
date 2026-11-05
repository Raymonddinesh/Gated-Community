"""Deterministic Financial Report Engine Application Service."""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.core.exceptions import NotFoundException
from apps.api.src.database.models.finance import (
    Account,
    FinancialReport,
    JournalEntry,
    JournalEntryLine,
)
from apps.api.src.database.repositories.audit_repository import AuditRepository
from apps.api.src.finance.domain.models import (
    AccountType,
    JournalStatus,
    NormalBalance,
    ReportStatus,
    ReportType,
    quantize_amount,
)
from apps.api.src.finance.infrastructure.repositories import (
    AccountRepository,
    FinancialReportRepository,
    PeriodRepository,
)


class ReportService:
    """
    Deterministic reporting engine.
    Calculates statements strictly from POSTED double-entry records. Zero AI calculations.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.account_repo = AccountRepository(session)
        self.period_repo = PeriodRepository(session)
        self.report_repo = FinancialReportRepository(session)
        self.audit_repo = AuditRepository(session)

    async def generate_trial_balance(
        self, society_id: UUID, financial_period_id: UUID, as_of_date: date | None = None
    ) -> dict[str, Any]:
        """
        Generate deterministic Trial Balance.
        Proves: Total Debits == Total Credits.
        """
        period = await self.period_repo.get_by_id(financial_period_id, society_id)
        if not period:
            raise NotFoundException("Financial period not found.")

        # Aggregate POSTED journal lines per account
        query = (
            select(
                Account.id,
                Account.account_code,
                Account.account_name,
                Account.account_type,
                Account.normal_balance,
                func.coalesce(func.sum(JournalEntryLine.debit_amount), 0).label("total_debit"),
                func.coalesce(func.sum(JournalEntryLine.credit_amount), 0).label("total_credit"),
            )
            .join(JournalEntryLine, Account.id == JournalEntryLine.account_id)
            .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
            .where(
                Account.society_id == society_id,
                JournalEntry.society_id == society_id,
                JournalEntry.financial_period_id == financial_period_id,
                JournalEntry.status == JournalStatus.POSTED.value,  # Strictly POSTED!
            )
        )
        if as_of_date:
            query = query.where(JournalEntry.entry_date <= as_of_date)

        query = query.group_by(
            Account.id,
            Account.account_code,
            Account.account_name,
            Account.account_type,
            Account.normal_balance,
        ).order_by(Account.account_code.asc())

        results = await self.session.execute(query)
        rows = results.all()

        line_items = []
        grand_total_debit = Decimal("0.0000")
        grand_total_credit = Decimal("0.0000")
        closing_debit_total = Decimal("0.0000")
        closing_credit_total = Decimal("0.0000")

        for r in rows:
            debit = quantize_amount(r.total_debit)
            credit = quantize_amount(r.total_credit)
            normal = r.normal_balance

            # Calculate closing balance according to normal balance rules
            if normal == NormalBalance.DEBIT.value:
                net = debit - credit
                closing_debit = net if net > 0 else Decimal("0.0000")
                closing_credit = -net if net < 0 else Decimal("0.0000")
            else:
                net = credit - debit
                closing_credit = net if net > 0 else Decimal("0.0000")
                closing_debit = -net if net < 0 else Decimal("0.0000")

            line_items.append(
                {
                    "account_id": str(r.id),
                    "account_code": r.account_code,
                    "account_name": r.account_name,
                    "account_type": r.account_type,
                    "normal_balance": r.normal_balance,
                    "total_debit": str(debit),
                    "total_credit": str(credit),
                    "closing_debit": str(closing_debit),
                    "closing_credit": str(closing_credit),
                }
            )

            grand_total_debit += debit
            grand_total_credit += credit
            closing_debit_total += closing_debit
            closing_credit_total += closing_credit

        is_balanced = grand_total_debit == grand_total_credit

        return {
            "society_id": str(society_id),
            "period_id": str(financial_period_id),
            "period_name": period.name,
            "as_of_date": (as_of_date or period.end_date).isoformat(),
            "currency": period.currency,
            "is_balanced": is_balanced,
            "grand_total_debit": str(grand_total_debit),
            "grand_total_credit": str(grand_total_credit),
            "total_debits": str(grand_total_debit),
            "total_credits": str(grand_total_credit),
            "closing_debit_total": str(closing_debit_total),
            "closing_credit_total": str(closing_credit_total),
            "discrepancy": str(abs(grand_total_debit - grand_total_credit)),
            "accounts": line_items,
        }

    async def generate_general_ledger(
        self,
        society_id: UUID,
        account_id: UUID,
        financial_period_id: UUID | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> dict[str, Any]:
        """Generate General Ledger running balance for a specific account."""
        account = await self.account_repo.get_by_id(account_id, society_id)
        if not account:
            raise NotFoundException("Account not found.")

        effective_start = start_date or from_date
        effective_end = end_date or to_date

        # Query all POSTED lines
        query = (
            select(JournalEntryLine, JournalEntry)
            .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
            .where(
                JournalEntryLine.account_id == account_id,
                JournalEntryLine.society_id == society_id,
                JournalEntry.status == JournalStatus.POSTED.value,
            )
        )
        if financial_period_id:
            query = query.where(JournalEntry.financial_period_id == financial_period_id)
        if effective_start:
            query = query.where(JournalEntry.entry_date >= effective_start)
        if effective_end:
            query = query.where(JournalEntry.entry_date <= effective_end)

        query = query.order_by(JournalEntry.entry_date.asc(), JournalEntry.created_at.asc())
        results = await self.session.execute(query)

        entries = []
        running_balance = Decimal("0.0000")
        total_debit = Decimal("0.0000")
        total_credit = Decimal("0.0000")

        for line, journal in results.all():
            d = quantize_amount(line.debit_amount)
            c = quantize_amount(line.credit_amount)
            total_debit += d
            total_credit += c

            if account.normal_balance == NormalBalance.DEBIT.value:
                running_balance += d - c
            else:
                running_balance += c - d

            entries.append(
                {
                    "journal_id": str(journal.id),
                    "journal_number": journal.journal_number,
                    "entry_date": journal.entry_date.isoformat(),
                    "description": line.description or journal.description,
                    "reference": journal.reference_number,
                    "debit": str(d),
                    "credit": str(c),
                    "running_balance": str(running_balance),
                }
            )

        return {
            "account_id": str(account.id),
            "account_code": account.account_code,
            "account_name": account.account_name,
            "account_type": account.account_type,
            "normal_balance": account.normal_balance,
            "currency": account.currency,
            "total_debit": str(total_debit),
            "total_credit": str(total_credit),
            "closing_balance": str(running_balance),
            "entries": entries,
        }

    async def generate_income_and_expenditure(
        self, society_id: UUID, financial_period_id: UUID
    ) -> dict[str, Any]:
        """
        Generate deterministic Income & Expenditure statement.
        Income (Credits) - Expenditure (Debits) = Net Surplus / Deficit.
        """
        period = await self.period_repo.get_by_id(financial_period_id, society_id)
        if not period:
            raise NotFoundException("Financial period not found.")

        # Query all income and expense accounts
        tb = await self.generate_trial_balance(society_id, financial_period_id)

        income_items = []
        expense_items = []
        total_income = Decimal("0.0000")
        total_expense = Decimal("0.0000")

        for row in tb["accounts"]:
            if row["account_type"] == AccountType.INCOME.value:
                # Income normal balance is credit: Net = Credit - Debit
                amount = quantize_amount(Decimal(row["total_credit"]) - Decimal(row["total_debit"]))
                income_items.append(
                    {"code": row["account_code"], "name": row["account_name"], "amount": str(amount)}
                )
                total_income += amount
            elif row["account_type"] == AccountType.EXPENSE.value:
                # Expense normal balance is debit: Net = Debit - Credit
                amount = quantize_amount(Decimal(row["total_debit"]) - Decimal(row["total_credit"]))
                expense_items.append(
                    {"code": row["account_code"], "name": row["account_name"], "amount": str(amount)}
                )
                total_expense += amount

        net_surplus = total_income - total_expense

        return {
            "society_id": str(society_id),
            "period_id": str(financial_period_id),
            "period_name": period.name,
            "currency": period.currency,
            "total_income": str(total_income),
            "total_expense": str(total_expense),
            "total_expenditure": str(total_expense),
            "net_surplus": str(net_surplus),
            "net_surplus_or_deficit": str(net_surplus),
            "is_surplus": net_surplus >= 0,
            "income_breakdown": income_items,
            "expense_breakdown": expense_items,
        }

    async def generate_balance_sheet(
        self, society_id: UUID, financial_period_id: UUID, as_of_date: date | None = None
    ) -> dict[str, Any]:
        """
        Generate deterministic Balance Sheet.
        Assets = Liabilities + Equity (Funds + Net Surplus).
        """
        period = await self.period_repo.get_by_id(financial_period_id, society_id)
        if not period:
            raise NotFoundException("Financial period not found.")

        tb = await self.generate_trial_balance(society_id, financial_period_id, as_of_date=as_of_date)
        inc_exp = await self.generate_income_and_expenditure(society_id, financial_period_id)
        net_surplus = Decimal(inc_exp["net_surplus_or_deficit"])

        assets = []
        liabilities = []
        equity = []

        total_assets = Decimal("0.0000")
        total_liabilities = Decimal("0.0000")
        total_equity = Decimal("0.0000")

        for row in tb["accounts"]:
            if row["account_type"] == AccountType.ASSET.value:
                bal = quantize_amount(Decimal(row["closing_debit"]) - Decimal(row["closing_credit"]))
                assets.append({"code": row["account_code"], "name": row["account_name"], "amount": str(bal)})
                total_assets += bal
            elif row["account_type"] == AccountType.LIABILITY.value:
                bal = quantize_amount(Decimal(row["closing_credit"]) - Decimal(row["closing_debit"]))
                liabilities.append(
                    {"code": row["account_code"], "name": row["account_name"], "amount": str(bal)}
                )
                total_liabilities += bal
            elif row["account_type"] == AccountType.EQUITY.value:
                bal = quantize_amount(Decimal(row["closing_credit"]) - Decimal(row["closing_debit"]))
                equity.append({"code": row["account_code"], "name": row["account_name"], "amount": str(bal)})
                total_equity += bal

        # Add current period net surplus/deficit to equity
        equity.append(
            {
                "code": "SURPLUS-DEFICIT",
                "name": "Current Period Net Surplus / (Deficit)",
                "amount": str(net_surplus),
            }
        )
        total_equity += net_surplus

        is_balanced = total_assets == (total_liabilities + total_equity)

        return {
            "society_id": str(society_id),
            "period_id": str(financial_period_id),
            "period_name": period.name,
            "currency": period.currency,
            "total_assets": str(total_assets),
            "total_liabilities": str(total_liabilities),
            "total_equity": str(total_equity),
            "liabilities_plus_equity": str(total_liabilities + total_equity),
            "total_liabilities_and_equity": str(total_liabilities + total_equity),
            "is_balanced": is_balanced,
            "assets": assets,
            "liabilities": liabilities,
            "equity": equity,
        }

    async def generate_receipts_and_payments(
        self, society_id: UUID, financial_period_id: UUID
    ) -> dict[str, Any]:
        """
        Generate Receipts & Payments statement.
        Summarizes cash/bank inflows (debits) and outflows (credits).
        """
        period = await self.period_repo.get_by_id(financial_period_id, society_id)
        if not period:
            raise NotFoundException("Financial period not found.")

        # Query all POSTED lines on bank or cash accounts
        query = (
            select(
                Account.account_code,
                Account.account_name,
                Account.sub_type,
                func.sum(JournalEntryLine.debit_amount).label("receipts"),
                func.sum(JournalEntryLine.credit_amount).label("payments"),
            )
            .join(JournalEntryLine, Account.id == JournalEntryLine.account_id)
            .join(JournalEntry, JournalEntryLine.journal_entry_id == JournalEntry.id)
            .where(
                Account.society_id == society_id,
                JournalEntry.financial_period_id == financial_period_id,
                JournalEntry.status == JournalStatus.POSTED.value,
                Account.sub_type.in_(["BANK", "CASH"]),
            )
            .group_by(Account.account_code, Account.account_name, Account.sub_type)
        )
        results = await self.session.execute(query)

        accounts_data = []
        total_receipts = Decimal("0.0000")
        total_payments = Decimal("0.0000")

        for r in results.all():
            rec = quantize_amount(r.receipts)
            pay = quantize_amount(r.payments)
            accounts_data.append(
                {
                    "code": r.account_code,
                    "name": r.account_name,
                    "sub_type": r.sub_type,
                    "receipts": str(rec),
                    "payments": str(pay),
                    "net_cash_flow": str(rec - pay),
                }
            )
            total_receipts += rec
            total_payments += pay

        return {
            "society_id": str(society_id),
            "period_id": str(financial_period_id),
            "period_name": period.name,
            "currency": period.currency,
            "total_receipts": str(total_receipts),
            "total_payments": str(total_payments),
            "net_flow": str(total_receipts - total_payments),
            "accounts": accounts_data,
        }

    async def save_and_publish_report(
        self,
        society_id: UUID,
        financial_period_id: UUID,
        report_type: str,
        name: str,
        user_id: UUID,
        publish_immediately: bool = False,
    ) -> FinancialReport:
        """Calculate report data and persist versioned snapshot."""
        if report_type == ReportType.TRIAL_BALANCE.value:
            data = await self.generate_trial_balance(society_id, financial_period_id)
        elif report_type == ReportType.INCOME_EXPENDITURE.value:
            data = await self.generate_income_and_expenditure(society_id, financial_period_id)
        elif report_type == ReportType.BALANCE_SHEET.value:
            data = await self.generate_balance_sheet(society_id, financial_period_id)
        elif report_type == ReportType.RECEIPTS_PAYMENTS.value:
            data = await self.generate_receipts_and_payments(society_id, financial_period_id)
        else:
            raise NotFoundException(f"Unsupported report type '{report_type}'.")

        status = ReportStatus.PUBLISHED.value if publish_immediately else ReportStatus.GENERATED.value

        report = await self.report_repo.save_report(
            society_id=society_id,
            financial_period_id=financial_period_id,
            report_type=report_type,
            name=name,
            report_data=data,
            generated_by=user_id,
            status=status,
        )

        if publish_immediately:
            await self.report_repo.update_status(report.id, "PUBLISHED", user_id)
            report.status = "PUBLISHED"

        await self.audit_repo.log_event(
            action="FINANCE_REPORT_GENERATED",
            entity_type="financial_report",
            entity_id=str(report.id),
            society_id=society_id,
            actor_user_id=user_id,
            after_state={"type": report_type, "version": report.version, "status": report.status},
        )

        return report
