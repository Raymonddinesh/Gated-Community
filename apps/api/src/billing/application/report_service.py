"""Billing and Revenue Reporting Application Service."""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.src.database.models.billing import Invoice, Payment
from apps.api.src.database.models.identity import User
from apps.api.src.database.models.society import Unit
from apps.api.src.finance.domain.models import quantize_amount


class BillingReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_collection_summary(self, society_id: UUID, period_id: UUID | None = None) -> dict[str, Any]:
        """Aggregate summary of billing, collections, adjustments, and outstanding dues."""
        query = select(
            func.coalesce(func.sum(Invoice.subtotal), Decimal("0.0000")),
            func.coalesce(func.sum(Invoice.adjustment_total), Decimal("0.0000")),
            func.coalesce(func.sum(Invoice.late_fee_total), Decimal("0.0000")),
            func.coalesce(func.sum(Invoice.grand_total), Decimal("0.0000")),
            func.coalesce(func.sum(Invoice.paid_amount), Decimal("0.0000")),
            func.coalesce(func.sum(Invoice.outstanding_amount), Decimal("0.0000")),
            func.count(Invoice.id),
        ).where(Invoice.society_id == society_id, Invoice.status != "CANCELLED")

        if period_id:
            query = query.where(Invoice.billing_period_id == period_id)

        res = await self.session.execute(query)
        row = res.one()

        # Payments collected
        pay_query = select(
            func.coalesce(func.sum(Payment.amount), Decimal("0.0000")),
            func.coalesce(func.sum(Payment.allocated_amount), Decimal("0.0000")),
            func.coalesce(func.sum(Payment.unallocated_amount), Decimal("0.0000")),
            func.count(Payment.id),
        ).where(Payment.society_id == society_id, Payment.status != "CANCELLED")

        pay_res = await self.session.execute(pay_query)
        pay_row = pay_res.one()

        return {
            "total_subtotal": str(quantize_amount(row[0])),
            "total_adjustments": str(quantize_amount(row[1])),
            "total_late_fees": str(quantize_amount(row[2])),
            "total_billed": str(quantize_amount(row[3])),
            "total_paid_against_invoices": str(quantize_amount(row[4])),
            "total_outstanding": str(quantize_amount(row[5])),
            "total_invoices_count": row[6],
            "total_payments_recorded": str(quantize_amount(pay_row[0])),
            "total_payments_allocated": str(quantize_amount(pay_row[1])),
            "total_payments_unallocated": str(quantize_amount(pay_row[2])),
            "total_payments_count": pay_row[3],
        }

    async def get_unit_wise_outstanding(self, society_id: UUID) -> list[dict[str, Any]]:
        """Outstanding dues grouped by physical unit."""
        query = (
            select(
                Unit.id,
                Unit.unit_number,
                func.coalesce(func.sum(Invoice.outstanding_amount), Decimal("0.0000")).label("outstanding"),
                func.count(Invoice.id).label("unpaid_invoices_count"),
            )
            .join(Invoice, Invoice.unit_id == Unit.id)
            .where(
                Invoice.society_id == society_id,
                Invoice.outstanding_amount > Decimal("0.0000"),
                Invoice.status.in_(["PUBLISHED", "PARTIALLY_PAID", "OVERDUE"]),
            )
            .group_by(Unit.id, Unit.unit_number)
            .order_by(Unit.unit_number.asc())
        )
        res = await self.session.execute(query)
        rows = res.all()
        return [
            {
                "unit_id": str(r[0]),
                "unit_number": r[1],
                "outstanding_amount": str(quantize_amount(r[2])),
                "unpaid_invoices_count": r[3],
            }
            for r in rows
        ]

    async def get_resident_wise_outstanding(self, society_id: UUID) -> list[dict[str, Any]]:
        """Outstanding dues grouped by responsible resident user."""
        query = (
            select(
                User.id,
                User.display_name,
                User.email,
                func.coalesce(func.sum(Invoice.outstanding_amount), Decimal("0.0000")).label("outstanding"),
                func.count(Invoice.id).label("unpaid_invoices_count"),
            )
            .join(Invoice, Invoice.responsible_user_id == User.id)
            .where(
                Invoice.society_id == society_id,
                Invoice.outstanding_amount > Decimal("0.0000"),
                Invoice.status.in_(["PUBLISHED", "PARTIALLY_PAID", "OVERDUE"]),
            )
            .group_by(User.id, User.display_name, User.email)
            .order_by(User.display_name.asc())
        )
        res = await self.session.execute(query)
        rows = res.all()
        return [
            {
                "user_id": str(r[0]),
                "display_name": r[1],
                "email": r[2],
                "outstanding_amount": str(quantize_amount(r[3])),
                "unpaid_invoices_count": r[4],
            }
            for r in rows
        ]

    async def get_aging_report(self, society_id: UUID, as_of_date: date | None = None) -> dict[str, Any]:
        """
        Group outstanding dues into aging buckets:
        0-30 days, 31-60 days, 61-90 days, 91-180 days, 181+ days overdue.
        """
        ref_date = as_of_date or date.today()
        query = (
            select(Invoice)
            .options(selectinload(Invoice.unit))
            .where(
                Invoice.society_id == society_id,
                Invoice.status.in_(["PUBLISHED", "PARTIALLY_PAID", "OVERDUE"]),
                Invoice.outstanding_amount > Decimal("0.0000"),
            )
        )
        res = await self.session.execute(query)
        invoices = list(res.scalars().all())

        buckets = {
            "current_or_0_to_30": Decimal("0.0000"),
            "31_to_60": Decimal("0.0000"),
            "61_to_90": Decimal("0.0000"),
            "91_to_180": Decimal("0.0000"),
            "181_plus": Decimal("0.0000"),
        }
        total_outstanding = Decimal("0.0000")

        for inv in invoices:
            total_outstanding += inv.outstanding_amount
            days_overdue = (ref_date - inv.due_date).days
            if days_overdue <= 30:
                buckets["current_or_0_to_30"] += inv.outstanding_amount
            elif 31 <= days_overdue <= 60:
                buckets["31_to_60"] += inv.outstanding_amount
            elif 61 <= days_overdue <= 90:
                buckets["61_to_90"] += inv.outstanding_amount
            elif 91 <= days_overdue <= 180:
                buckets["91_to_180"] += inv.outstanding_amount
            else:
                buckets["181_plus"] += inv.outstanding_amount

        return {
            "as_of_date": ref_date.isoformat(),
            "total_outstanding": str(quantize_amount(total_outstanding)),
            "aging_buckets": {k: str(quantize_amount(v)) for k, v in buckets.items()},
            "invoices_analyzed": len(invoices),
        }

    async def get_payment_method_summary(self, society_id: UUID) -> list[dict[str, Any]]:
        """Summarize payments by payment method (CASH, BANK_TRANSFER, UPI, etc.)."""
        query = (
            select(
                Payment.payment_method,
                func.count(Payment.id),
                func.coalesce(func.sum(Payment.amount), Decimal("0.0000")),
                func.coalesce(func.sum(Payment.allocated_amount), Decimal("0.0000")),
                func.coalesce(func.sum(Payment.unallocated_amount), Decimal("0.0000")),
            )
            .where(Payment.society_id == society_id, Payment.status != "CANCELLED")
            .group_by(Payment.payment_method)
            .order_by(Payment.payment_method.asc())
        )
        res = await self.session.execute(query)
        rows = res.all()
        return [
            {
                "payment_method": r[0],
                "count": r[1],
                "total_amount": str(quantize_amount(r[2])),
                "total_allocated": str(quantize_amount(r[3])),
                "total_unallocated": str(quantize_amount(r[4])),
            }
            for r in rows
        ]

    async def get_unallocated_payments_report(self, society_id: UUID) -> list[dict[str, Any]]:
        """List all payments that have advance or unallocated balances."""
        query = (
            select(Payment)
            .options(selectinload(Payment.payer_user))
            .where(
                Payment.society_id == society_id,
                Payment.unallocated_amount > Decimal("0.0000"),
                Payment.status.in_(["RECORDED", "CLEARED", "PARTIALLY_ALLOCATED"]),
            )
            .order_by(Payment.payment_date.desc())
        )
        res = await self.session.execute(query)
        payments = list(res.scalars().all())
        return [
            {
                "payment_id": str(p.id),
                "reference_number": p.reference_number,
                "payment_date": p.payment_date.isoformat(),
                "payment_method": p.payment_method,
                "payer_name": p.payer_user.display_name if p.payer_user else "Unknown",
                "amount": str(p.amount),
                "allocated_amount": str(p.allocated_amount),
                "unallocated_amount": str(p.unallocated_amount),
                "status": p.status,
            }
            for p in payments
        ]
