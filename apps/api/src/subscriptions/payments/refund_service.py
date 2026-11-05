"""Phase 21E.3 — SaaS Refund Management Service.

Handles full and partial refunds for captured SaaS subscription payments:
- Validates remaining refundable balance against previous partial refunds.
- Calls payment gateway provider to execute outbound transfer.
- Updates PlatformPayment status (PARTIALLY_REFUNDED / REFUNDED) and refunded_amount.
- Preserves immutable PlatformRefund history.
- Mandatory Invariant: A refund NEVER automatically generates a statutory credit note.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.core.tenant_context import tenant_context
from apps.api.src.database.models.platform_billing import (
    PlatformPayment,
    PlatformRefund,
    PlatformSubscriptionAuditLog,
)
from apps.api.src.database.session import set_db_tenant_context
from apps.api.src.subscriptions.payments.exceptions import (
    InvalidRefundAmountException,
    PaymentNotFoundException,
    RefundFailedException,
)
from apps.api.src.subscriptions.payments.provider import PaymentGatewayProvider
from apps.api.src.subscriptions.payments.provider_factory import PaymentGatewayFactory
from apps.api.src.subscriptions.payments.schemas import RefundResponse

logger = logging.getLogger("societysphere.payments.refund")


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class RefundService:
    """Domain service managing refund lifecycle, provider calls, and payment balance adjustments."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def initiate_refund(
        self,
        society_id: UUID,
        payment_id: UUID,
        amount: Decimal | None = None,
        reason: str = "Requested refund",
        initiated_by: str = "SYSTEM",
        custom_provider: PaymentGatewayProvider | None = None,
    ) -> RefundResponse:
        """Initiate a full or partial refund against a captured payment.

        Guarantees:
        - Row-level lock on PlatformPayment prevents concurrent double-refunding.
        - Checks remaining refundable balance: (payment.amount - payment.refunded_amount).
        - Outbound gateway call via PaymentGatewayProvider.
        - Updates payment.status to PARTIALLY_REFUNDED or REFUNDED.
        - Never automatically generates a credit note.
        """
        async with tenant_context(society_id):
            await set_db_tenant_context(self.session, society_id)

            # 1. Fetch payment with pessimistic lock
            stmt = (
                select(PlatformPayment)
                .where(
                    PlatformPayment.id == payment_id,
                    PlatformPayment.society_id == society_id,
                )
                .with_for_update()
            )
            res = await self.session.execute(stmt)
            payment = res.scalar_one_or_none()
            if not payment:
                raise PaymentNotFoundException(payment_id=payment_id)

            # 2. Check refundable balance
            available_balance = (payment.amount - payment.refunded_amount).quantize(Decimal("0.01"))
            if available_balance <= Decimal("0.00"):
                raise InvalidRefundAmountException(
                    payment_id=payment_id,
                    requested_amount=str(amount or "0.00"),
                    available_amount=str(available_balance),
                )

            # 3. Determine refund amount
            refund_amount = (
                amount.quantize(Decimal("0.01")) if amount is not None else available_balance
            )
            if refund_amount <= Decimal("0.00") or refund_amount > available_balance:
                raise InvalidRefundAmountException(
                    payment_id=payment_id,
                    requested_amount=str(refund_amount),
                    available_amount=str(available_balance),
                )

            # 4. Resolve gateway provider
            provider = custom_provider or await PaymentGatewayFactory.get_provider(
                self.session, payment.gateway_provider
            )

            # 5. Execute gateway refund
            try:
                gateway_res = await provider.initiate_refund(
                    payment_id=payment.gateway_payment_id,
                    amount=refund_amount,
                    currency=payment.currency_code,
                    reason=reason,
                )
            except Exception as exc:
                logger.error(
                    "Gateway refund failed for payment %s (%s): %s",
                    payment_id,
                    payment.gateway_payment_id,
                    exc,
                )
                raise RefundFailedException(payment_id=payment_id, reason=str(exc)) from exc

            # 6. Record PlatformRefund
            now = _utc_now()
            is_completed = gateway_res.status in ("processed", "completed", "succeeded")
            refund_record = PlatformRefund(
                society_id=society_id,
                payment_id=payment.id,
                gateway_provider=payment.gateway_provider,
                gateway_refund_id=gateway_res.refund_id,
                amount=refund_amount,
                currency_code=payment.currency_code,
                reason=reason[:100],
                status="COMPLETED" if is_completed else "INITIATED",
                initiated_by=initiated_by,
                processed_at=now if is_completed else None,
            )
            self.session.add(refund_record)

            # 7. Update PlatformPayment refunded_amount and status
            new_refunded = (payment.refunded_amount + refund_amount).quantize(Decimal("0.01"))
            payment.refunded_amount = new_refunded
            if new_refunded >= payment.amount:
                payment.status = "REFUNDED"
            else:
                payment.status = "PARTIALLY_REFUNDED"

            await self.session.flush()

            # 8. Record audit log
            audit = PlatformSubscriptionAuditLog(
                society_id=society_id,
                entity_type="REFUND",
                entity_id=refund_record.id,
                action="REFUND_INITIATED",
                actor_type="SYSTEM" if initiated_by == "SYSTEM" else "USER",
                actor_id=None,
                before_state={"payment_refunded_before": str(payment.refunded_amount - refund_amount)},
                after_state={
                    "refund_id": str(refund_record.id),
                    "gateway_refund_id": refund_record.gateway_refund_id,
                    "amount": str(refund_amount),
                    "payment_status": payment.status,
                },
            )
            self.session.add(audit)

            return RefundResponse(
                refund_id=refund_record.id,
                payment_id=payment.id,
                gateway_refund_id=refund_record.gateway_refund_id,
                amount=refund_amount,
                currency_code=refund_record.currency_code,
                status=refund_record.status,
                reason=refund_record.reason,
                initiated_by=refund_record.initiated_by,
                created_at=refund_record.created_at or now,
                processed_at=refund_record.processed_at,
            )
