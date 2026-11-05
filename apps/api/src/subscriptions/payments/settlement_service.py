"""Phase 21E.3 — Atomic Payment Settlement Service.

Orchestrates atomic financial settlement for captured payments:
- Records PlatformPayment with row-level pessimistic locking.
- Transitions PlatformInvoice status (ISSUED/OVERDUE -> PAID/PARTIALLY_PAID).
- Coordinates with SubscriptionLifecycleService:
  * Transitions PAST_DUE -> ACTIVE only after confirmed settlement.
  * Preserves administrative society suspension (Society.status == SUSPENDED).
  * Enforces terminal CANCELLED subscription invariant (never reactivates).
  * Automatically initiates refund for orphaned payments on CANCELLED subscriptions.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.core.tenant_context import tenant_context
from apps.api.src.database.models.platform_billing import (
    PlatformDunningAttempt,
    PlatformInvoice,
    PlatformPayment,
    PlatformPaymentAttempt,
    PlatformSubscriptionAuditLog,
    PlatformSubscriptionHistory,
)
from apps.api.src.database.models.society import Society
from apps.api.src.database.models.subscription import SocietySubscription
from apps.api.src.database.session import set_db_tenant_context
from apps.api.src.subscriptions.enums import SubscriptionStatus
from apps.api.src.subscriptions.payments.provider import PaymentGatewayProvider
from apps.api.src.subscriptions.payments.refund_service import RefundService
from apps.api.src.subscriptions.subscription_lifecycle_service import SubscriptionLifecycleService

logger = logging.getLogger("societysphere.payments.settlement")


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class PaymentSettlementService:
    """Atomic domain service for settling captured payments and reconciling invoices."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def settle_payment(
        self,
        society_id: UUID,
        gateway_provider: str,
        gateway_payment_id: str,
        amount: Decimal,
        invoice_id: UUID | None = None,
        currency: str = "INR",
        payment_method: str = "CARD",
        captured_at: datetime | None = None,
        card_network: str | None = None,
        card_last4: str | None = None,
        upi_vpa: str | None = None,
        gateway_fee: Decimal = Decimal("0.00"),
        gateway_tax: Decimal = Decimal("0.00"),
        payment_attempt_id: UUID | None = None,
        custom_provider: PaymentGatewayProvider | None = None,
    ) -> PlatformPayment:
        """Atomically record captured payment, settle invoice, and evaluate subscription lifecycle.

        Guarantees:
        - FORCE RLS enforcement through tenant_context(society_id).
        - Idempotency: Duplicate captures return existing payment record without double-crediting.
        - Terminal Cancelled State: Cancelled subscriptions are never reactivated; orphaned
          payments are flagged and refunded.
        - Society Decoupling: Settling an invoice never reactivates an administratively suspended society.
        """
        now = _utc_now()
        effective_captured_at = captured_at or now

        async with tenant_context(society_id):
            await set_db_tenant_context(self.session, society_id)

            # 1. Idempotency Check: Existing PlatformPayment
            stmt_pay = select(PlatformPayment).where(
                PlatformPayment.gateway_provider == gateway_provider,
                PlatformPayment.gateway_payment_id == gateway_payment_id,
            )
            res_pay = await self.session.execute(stmt_pay)
            existing_pay = res_pay.scalar_one_or_none()
            if existing_pay:
                logger.info(
                    "Payment %s:%s already recorded. Returning idempotent settlement.",
                    gateway_provider,
                    gateway_payment_id,
                )
                return existing_pay

            # 2. Fetch and lock invoice if provided
            invoice: PlatformInvoice | None = None
            if invoice_id:
                stmt_inv = (
                    select(PlatformInvoice)
                    .where(
                        PlatformInvoice.id == invoice_id,
                        PlatformInvoice.society_id == society_id,
                    )
                    .with_for_update()
                )
                invoice = (await self.session.execute(stmt_inv)).scalar_one_or_none()

            # 3. Fetch and lock subscription
            sub: SocietySubscription | None = None
            if invoice:
                stmt_sub = (
                    select(SocietySubscription)
                    .where(SocietySubscription.id == invoice.subscription_id)
                    .with_for_update()
                )
                sub = (await self.session.execute(stmt_sub)).scalar_one_or_none()
            else:
                stmt_sub = (
                    select(SocietySubscription)
                    .where(SocietySubscription.society_id == society_id)
                    .with_for_update()
                )
                sub = (await self.session.execute(stmt_sub)).scalar_one_or_none()

            # 4. Fetch Society for decoupling check
            stmt_soc = select(Society).where(Society.id == society_id).with_for_update()
            soc = (await self.session.execute(stmt_soc)).scalar_one_or_none()

            # 5. Check Terminal Cancelled Subscription Invariant
            if sub and sub.status == SubscriptionStatus.CANCELLED.value:
                logger.warning(
                    "Late payment captured for CANCELLED subscription (society: %s, sub: %s). "
                    "Flagging as orphaned and initiating refund.",
                    society_id,
                    sub.id,
                )
                orphaned_payment = PlatformPayment(
                    society_id=society_id,
                    invoice_id=invoice.id if invoice else None,
                    payment_attempt_id=payment_attempt_id,
                    gateway_provider=gateway_provider,
                    gateway_payment_id=gateway_payment_id,
                    payment_method=payment_method,
                    amount=amount,
                    refunded_amount=Decimal("0.00"),
                    currency_code=currency,
                    status="CAPTURED",
                    reconciliation_status="ORPHAN_ON_CANCELLED_SUBSCRIPTION",
                    captured_at=effective_captured_at,
                    card_network=card_network,
                    card_last4=card_last4,
                    upi_vpa=upi_vpa,
                    gateway_fee=gateway_fee,
                    gateway_tax=gateway_tax,
                    is_settled=False,
                    settled_at=None,
                )
                self.session.add(orphaned_payment)
                await self.session.flush()

                # Trigger refund service for orphaned payment
                refund_service = RefundService(self.session)
                await refund_service.initiate_refund(
                    society_id=society_id,
                    payment_id=orphaned_payment.id,
                    amount=amount,
                    reason="ORPHAN_PAYMENT_ON_CANCELLED_SUBSCRIPTION",
                    initiated_by="SYSTEM",
                    custom_provider=custom_provider,
                )
                return orphaned_payment

            # 6. Standard Valid Settlement
            payment = PlatformPayment(
                society_id=society_id,
                invoice_id=invoice.id if invoice else None,
                payment_attempt_id=payment_attempt_id,
                gateway_provider=gateway_provider,
                gateway_payment_id=gateway_payment_id,
                payment_method=payment_method,
                amount=amount,
                refunded_amount=Decimal("0.00"),
                currency_code=currency,
                status="CAPTURED",
                reconciliation_status="RECONCILED",
                captured_at=effective_captured_at,
                card_network=card_network,
                card_last4=card_last4,
                upi_vpa=upi_vpa,
                gateway_fee=gateway_fee,
                gateway_tax=gateway_tax,
                is_settled=True,
                settled_at=now,
            )
            self.session.add(payment)
            await self.session.flush()

            # 7. Update Payment Attempt if linked
            if payment_attempt_id:
                stmt_att = select(PlatformPaymentAttempt).where(
                    PlatformPaymentAttempt.id == payment_attempt_id,
                    PlatformPaymentAttempt.society_id == society_id,
                )
                attempt = (await self.session.execute(stmt_att)).scalar_one_or_none()
                if attempt:
                    attempt.status = "SUCCEEDED"

            # 8. Update Invoice
            if invoice:
                new_paid = (invoice.amount_paid + amount).quantize(Decimal("0.01"))
                invoice.amount_paid = new_paid
                new_due = max(Decimal("0.00"), invoice.grand_total - new_paid).quantize(Decimal("0.01"))
                invoice.amount_due = new_due

                if new_due == Decimal("0.00"):
                    invoice.status = "PAID"
                    invoice.paid_at = now
                else:
                    invoice.status = "PARTIALLY_PAID"

            # 9. Evaluate Subscription Lifecycle Transition
            inv_desc = (
                f"Invoice {invoice.invoice_number or invoice.id}"
                if invoice
                else f"Payment {gateway_payment_id}"
            )
            if sub and sub.status == SubscriptionStatus.PAST_DUE.value:
                # MANDATORY INVARIANT: Decouple Society.status from SocietySubscription.status!
                # If society is administratively SUSPENDED, payment settlement does NOT reactivate it.
                lifecycle_service = SubscriptionLifecycleService(self.session)
                await lifecycle_service.transition_status(
                    society_id=society_id,
                    target_status=SubscriptionStatus.ACTIVE,
                    reason=f"{inv_desc} settled via {gateway_provider}",
                    actor_id=None,
                )
                if soc and soc.status == "SUSPENDED":
                    logger.info(
                        "Society %s remains administratively SUSPENDED despite subscription settlement.",
                        society_id,
                    )
            elif sub and sub.status == SubscriptionStatus.SUSPENDED.value:
                # MANDATORY CONDITION: Late payment recovery after dunning suspension.
                # A payment received after suspension may restore subscription service ONLY when
                # the subscription was suspended specifically by the automated dunning workflow on this invoice.
                # If suspended for another reason (e.g. administrative/fraud/TOS), DO NOT reactivate!

                # 1. Query latest transition into SUSPENDED from immutable PlatformSubscriptionHistory
                stmt_hist = (
                    select(PlatformSubscriptionHistory)
                    .where(
                        PlatformSubscriptionHistory.society_id == society_id,
                        PlatformSubscriptionHistory.subscription_id == sub.id,
                    )
                    .order_by(
                        PlatformSubscriptionHistory.effective_at.desc(),
                        PlatformSubscriptionHistory.created_at.desc(),
                    )
                    .limit(1)
                )
                latest_hist = (await self.session.execute(stmt_hist)).scalar_one_or_none()

                # 2. Query Day 7 suspension attempt from PlatformDunningAttempt
                stmt_dunning = (
                    select(PlatformDunningAttempt)
                    .where(
                        PlatformDunningAttempt.society_id == society_id,
                        PlatformDunningAttempt.subscription_id == sub.id,
                        PlatformDunningAttempt.invoice_id == (invoice.id if invoice else None),
                        PlatformDunningAttempt.attempt_type.in_(["DAY_7_SUSPENSION", "SUSPENSION_EXECUTION"]),
                        PlatformDunningAttempt.status == "SUCCEEDED",
                    )
                    .order_by(PlatformDunningAttempt.executed_at.desc())
                    .limit(1)
                )
                dunning_att = (await self.session.execute(stmt_dunning)).scalar_one_or_none()

                is_dunning_suspension = (
                    latest_hist is not None
                    and latest_hist.new_status == SubscriptionStatus.SUSPENDED.value
                    and latest_hist.transition_reason.startswith("DUNNING_")
                    and latest_hist.changed_by is None
                    and dunning_att is not None
                )

                if is_dunning_suspension:
                    lifecycle_service = SubscriptionLifecycleService(self.session)
                    await lifecycle_service.transition_status(
                        society_id=society_id,
                        target_status=SubscriptionStatus.ACTIVE,
                        reason=f"{inv_desc} settled via {gateway_provider}; dunning suspension lifted",
                        actor_id=None,
                    )
                    logger.info(
                        "Subscription %s reactivated from dunning suspension upon settlement of invoice %s.",
                        sub.id,
                        invoice.id if invoice else "unknown",
                    )
                    if soc and soc.status == "SUSPENDED":
                        logger.info(
                            "Society %s remains administratively SUSPENDED despite subscription settlement.",
                            society_id,
                        )
                else:
                    logger.warning(
                        "Subscription %s is SUSPENDED for non-dunning/administrative reasons. "
                        "Payment settled but subscription was NOT reactivated.",
                        sub.id,
                    )
            elif sub and sub.status == SubscriptionStatus.TRIAL.value:
                # Transition TRIAL -> ACTIVE on confirmed first billing payment
                lifecycle_service = SubscriptionLifecycleService(self.session)
                await lifecycle_service.transition_status(
                    society_id=society_id,
                    target_status=SubscriptionStatus.ACTIVE,
                    reason=f"{inv_desc} settled; trial converted to active",
                    actor_id=None,
                )

            # 10. Audit Log
            audit = PlatformSubscriptionAuditLog(
                society_id=society_id,
                entity_type="PAYMENT",
                entity_id=payment.id,
                action="PAYMENT_CAPTURED",
                actor_type="GATEWAY",
                actor_id=None,
                before_state=None,
                after_state={
                    "gateway_provider": gateway_provider,
                    "gateway_payment_id": gateway_payment_id,
                    "amount": str(amount),
                    "invoice_id": str(invoice.id) if invoice else None,
                    "settled": True,
                },
            )
            self.session.add(audit)
            await self.session.flush()
            return payment
