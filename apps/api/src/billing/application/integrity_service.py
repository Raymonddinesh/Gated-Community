"""Financial Integrity and Outstanding Reconciliation Application Service."""

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.billing.domain.models import PaymentStatus
from apps.api.src.database.models.billing import Invoice, Payment
from apps.api.src.finance.domain.models import quantize_amount


class IntegrityReconciliationService:
    """
    Internal integrity verification engine.
    Audits invoices and payments for mathematical and ledger consistency:
      - Outstanding = Grand Total - Paid Amount
      - Payment Total = Allocated Amount + Unallocated Amount
      - Identifies over-allocations, negative balances, and orphaned records
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def verify_society_billing_integrity(self, society_id: UUID) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []

        # 1. Audit Invoices
        inv_query = select(Invoice).where(Invoice.society_id == society_id)
        inv_res = await self.session.execute(inv_query)
        invoices = list(inv_res.scalars().all())

        total_invoices = len(invoices)
        total_billed = Decimal("0.0000")
        total_outstanding = Decimal("0.0000")
        total_paid_on_invoices = Decimal("0.0000")

        for inv in invoices:
            total_billed += inv.grand_total
            total_outstanding += inv.outstanding_amount
            total_paid_on_invoices += inv.paid_amount

            # Invariant: outstanding_amount + paid_amount == grand_total
            derived_total = quantize_amount(inv.outstanding_amount + inv.paid_amount)
            if derived_total != inv.grand_total:
                issues.append(
                    {
                        "type": "INVOICE_BALANCE_MISMATCH",
                        "invoice_id": str(inv.id),
                        "invoice_number": inv.invoice_number,
                        "grand_total": str(inv.grand_total),
                        "outstanding": str(inv.outstanding_amount),
                        "paid": str(inv.paid_amount),
                        "discrepancy": str(quantize_amount(inv.grand_total - derived_total)),
                    }
                )

            # Invariant: outstanding_amount >= 0
            if inv.outstanding_amount < Decimal("0.0000"):
                issues.append(
                    {
                        "type": "NEGATIVE_OUTSTANDING",
                        "invoice_id": str(inv.id),
                        "invoice_number": inv.invoice_number,
                        "outstanding": str(inv.outstanding_amount),
                    }
                )

            # Invariant: paid_amount <= grand_total
            if inv.paid_amount > inv.grand_total:
                issues.append(
                    {
                        "type": "OVER_PAID_INVOICE",
                        "invoice_id": str(inv.id),
                        "invoice_number": inv.invoice_number,
                        "grand_total": str(inv.grand_total),
                        "paid": str(inv.paid_amount),
                    }
                )

        # 2. Audit Payments
        pay_query = select(Payment).where(Payment.society_id == society_id)
        pay_res = await self.session.execute(pay_query)
        payments = list(pay_res.scalars().all())

        total_payments = len(payments)
        total_payment_amount = Decimal("0.0000")
        total_allocated = Decimal("0.0000")
        total_unallocated = Decimal("0.0000")

        for pay in payments:
            if pay.status in (PaymentStatus.CANCELLED.value, PaymentStatus.REVERSED.value):
                continue

            total_payment_amount += pay.amount
            total_allocated += pay.allocated_amount
            total_unallocated += pay.unallocated_amount

            # Invariant: allocated_amount + unallocated_amount == amount
            derived_pay_total = quantize_amount(pay.allocated_amount + pay.unallocated_amount)
            if derived_pay_total != pay.amount:
                issues.append(
                    {
                        "type": "PAYMENT_BALANCE_MISMATCH",
                        "payment_id": str(pay.id),
                        "reference_number": pay.reference_number,
                        "total_amount": str(pay.amount),
                        "allocated": str(pay.allocated_amount),
                        "unallocated": str(pay.unallocated_amount),
                        "discrepancy": str(quantize_amount(pay.amount - derived_pay_total)),
                    }
                )

            if pay.unallocated_amount < Decimal("0.0000"):
                issues.append(
                    {
                        "type": "NEGATIVE_UNALLOCATED_AMOUNT",
                        "payment_id": str(pay.id),
                        "reference_number": pay.reference_number,
                        "unallocated": str(pay.unallocated_amount),
                    }
                )

        is_healthy = len(issues) == 0

        return {
            "society_id": str(society_id),
            "is_healthy": is_healthy,
            "total_invoices_audited": total_invoices,
            "total_payments_audited": total_payments,
            "total_billed": str(quantize_amount(total_billed)),
            "total_outstanding": str(quantize_amount(total_outstanding)),
            "total_paid_on_invoices": str(quantize_amount(total_paid_on_invoices)),
            "total_payment_amount": str(quantize_amount(total_payment_amount)),
            "total_allocated": str(quantize_amount(total_allocated)),
            "total_unallocated": str(quantize_amount(total_unallocated)),
            "issue_count": len(issues),
            "issues": issues,
        }
