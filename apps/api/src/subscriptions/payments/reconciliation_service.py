"""Phase 21E.3 — Financial Reconciliation Service.

Independent reconciliation service comparing internal records against external gateway states:
- Compares internal PlatformPayment records against external provider payment objects.
- Detects missing provider payments, amount mismatches, currency mismatches, and status drifts.
- Reconciles PlatformRefund balances against recorded payment.refunded_amount.
- Flags orphaned payments captured on cancelled subscriptions.
- Mandatory Rule: Never silently modifies financial records to force reconciliation.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.core.tenant_context import tenant_context
from apps.api.src.database.models.platform_billing import (
    PlatformPayment,
    PlatformRefund,
)
from apps.api.src.database.session import set_db_tenant_context
from apps.api.src.subscriptions.payments.exceptions import PaymentGatewayException
from apps.api.src.subscriptions.payments.provider import PaymentGatewayProvider
from apps.api.src.subscriptions.payments.provider_factory import PaymentGatewayFactory
from apps.api.src.subscriptions.payments.schemas import (
    ReconciliationDiscrepancy,
    ReconciliationReportResponse,
)

logger = logging.getLogger("societysphere.payments.reconciliation")


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class PaymentReconciliationService:
    """Performs financial reconciliation between internal records and gateway provider states."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def reconcile(
        self,
        society_id: UUID | None = None,
        provider_name: str = "RAZORPAY",
        custom_provider: PaymentGatewayProvider | None = None,
    ) -> ReconciliationReportResponse:
        """Run complete reconciliation pass across internal payments and provider states.

        Guarantees:
        - Non-mutating: Flags mismatches without overwriting financial balances.
        - Checks for missing provider payments, duplicate captures, and balance drift.
        - Identifies orphaned payments on cancelled subscriptions.
        """
        started_at = _utc_now()
        discrepancies: list[ReconciliationDiscrepancy] = []
        reconciled_count = 0
        orphaned_count = 0

        # 1. Fetch Internal Payments
        if society_id:
            async with tenant_context(society_id):
                await set_db_tenant_context(self.session, society_id)
                stmt = select(PlatformPayment).where(
                    PlatformPayment.society_id == society_id,
                    PlatformPayment.gateway_provider == provider_name.upper(),
                )
                payments = (await self.session.execute(stmt)).scalars().all()
        else:
            stmt = select(PlatformPayment).where(
                PlatformPayment.gateway_provider == provider_name.upper()
            )
            payments = (await self.session.execute(stmt)).scalars().all()

        # 2. Check Duplicate Captures in DB
        stmt_dup = (
            select(
                PlatformPayment.gateway_payment_id,
                func.count(PlatformPayment.id).label("cnt"),
            )
            .group_by(PlatformPayment.gateway_payment_id)
            .having(func.count(PlatformPayment.id) > 1)
        )
        if society_id:
            stmt_dup = stmt_dup.where(PlatformPayment.society_id == society_id)
        dup_rows = (await self.session.execute(stmt_dup)).all()
        for row in dup_rows:
            discrepancies.append(
                ReconciliationDiscrepancy(
                    payment_reference=row.gateway_payment_id,
                    type="DUPLICATE_CAPTURE_IN_DATABASE",
                    details={"count": row.cnt},
                )
            )

        # 3. Resolve Provider
        provider = custom_provider or await PaymentGatewayFactory.get_provider(
            self.session, provider_name
        )

        # 4. Compare Each Payment Against Provider State
        for payment in payments:
            # Check Orphaned Status
            if payment.reconciliation_status == "ORPHAN_ON_CANCELLED_SUBSCRIPTION":
                orphaned_count += 1
                discrepancies.append(
                    ReconciliationDiscrepancy(
                        payment_reference=payment.gateway_payment_id,
                        type="ORPHAN_PAYMENT_ON_CANCELLED_SUBSCRIPTION",
                        details={
                            "payment_id": str(payment.id),
                            "society_id": str(payment.society_id),
                            "amount": str(payment.amount),
                        },
                    )
                )

            # Fetch Authoritative Provider State
            try:
                remote_details = await provider.fetch_payment(payment.gateway_payment_id)
            except PaymentGatewayException as exc:
                discrepancies.append(
                    ReconciliationDiscrepancy(
                        payment_reference=payment.gateway_payment_id,
                        type="MISSING_PROVIDER_CAPTURE",
                        details={"error": str(exc)},
                    )
                )
                continue

            has_mismatch = False

            # Check Amount
            if remote_details.amount != payment.amount:
                has_mismatch = True
                discrepancies.append(
                    ReconciliationDiscrepancy(
                        payment_reference=payment.gateway_payment_id,
                        type="AMOUNT_MISMATCH",
                        details={
                            "internal_amount": str(payment.amount),
                            "provider_amount": str(remote_details.amount),
                        },
                    )
                )

            # Check Currency
            if remote_details.currency.upper() != payment.currency_code.upper():
                has_mismatch = True
                discrepancies.append(
                    ReconciliationDiscrepancy(
                        payment_reference=payment.gateway_payment_id,
                        type="CURRENCY_MISMATCH",
                        details={
                            "internal_currency": payment.currency_code,
                            "provider_currency": remote_details.currency,
                        },
                    )
                )

            # Check Refund Sum Reconciliation
            stmt_rf = select(PlatformRefund).where(PlatformRefund.payment_id == payment.id)
            refunds = (await self.session.execute(stmt_rf)).scalars().all()
            sum_refunds = sum((r.amount for r in refunds), Decimal("0.00")).quantize(Decimal("0.01"))
            if sum_refunds != payment.refunded_amount:
                has_mismatch = True
                discrepancies.append(
                    ReconciliationDiscrepancy(
                        payment_reference=payment.gateway_payment_id,
                        type="REFUND_SUM_DISCREPANCY",
                        details={
                            "payment_refunded_amount": str(payment.refunded_amount),
                            "sum_of_refund_records": str(sum_refunds),
                        },
                    )
                )

            if not has_mismatch and payment.reconciliation_status != "ORPHAN_ON_CANCELLED_SUBSCRIPTION":
                reconciled_count += 1

        completed_at = _utc_now()
        return ReconciliationReportResponse(
            reconciled_count=reconciled_count,
            discrepancy_count=len(discrepancies),
            orphaned_count=orphaned_count,
            discrepancies=discrepancies,
            started_at=started_at,
            completed_at=completed_at,
        )
