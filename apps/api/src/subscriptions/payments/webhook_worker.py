"""Phase 21E.3 — Asynchronous Webhook Processing Worker.

Processes durably ingested PlatformWebhookEvent records:
- Supplementary Concurrency Control via PostgreSQL 64-bit advisory locks (pg_try_advisory_xact_lock).
- Lock conflicts trigger safe retry without dropped events.
- Transaction boundaries with atomic settlement and invoice reconciliation.
- Dead-letter handling: marks events FAILED after max retries with sanitized diagnostics.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.database.models.platform_billing import (
    PlatformInvoice,
    PlatformPaymentAttempt,
    PlatformRefund,
    PlatformWebhookEvent,
)
from apps.api.src.subscriptions.payments.exceptions import (
    LockAcquisitionException,
    PaymentDomainException,
)
from apps.api.src.subscriptions.payments.provider import PaymentGatewayProvider
from apps.api.src.subscriptions.payments.settlement_service import PaymentSettlementService

logger = logging.getLogger("societysphere.payments.webhook_worker")

MAX_RETRIES = 3


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class WebhookProcessingWorker:
    """Asynchronous worker for executing durable webhook events."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settlement_service = PaymentSettlementService(session)

    async def process_webhook_event(
        self,
        event_id: str,
        provider: str = "RAZORPAY",
        custom_provider: PaymentGatewayProvider | None = None,
    ) -> PlatformWebhookEvent | None:
        """Process a persisted webhook event with transactional boundaries and advisory locking.

        Guarantees:
        - Advisory lock serialization on deterministic 64-bit lock_key.
        - Lock acquisition failure rolls back and raises LockAcquisitionException (safe retry).
        - Prevents duplicate settlement on repeated deliveries.
        - Records sanitized errors and transitions to FAILED upon retry exhaustion.
        """
        norm_provider = provider.upper().strip()

        # 1. Fetch event under row lock
        stmt = (
            select(PlatformWebhookEvent)
            .where(
                PlatformWebhookEvent.gateway_provider == norm_provider,
                PlatformWebhookEvent.event_id == event_id,
            )
            .with_for_update()
        )
        res = await self.session.execute(stmt)
        event = res.scalar_one_or_none()
        if not event:
            logger.warning("Webhook event %s:%s not found for processing", norm_provider, event_id)
            return None

        # Short-circuit if already processed or skipped
        if event.processing_status in ("PROCESSED", "PROCESSED_REFUND_INITIATED", "SKIPPED"):
            logger.info(
                "Webhook event %s:%s already in terminal state %s",
                norm_provider,
                event_id,
                event.processing_status,
            )
            return event

        # 2. Supplementary Advisory Lock Concurrency Control (PostgreSQL)
        is_pg = False
        try:
            bind = self.session.get_bind()
            if bind and "postgresql" in str(bind.dialect.name).lower():
                is_pg = True
        except Exception:
            pass

        current_lock_key = event.lock_key
        if is_pg:
            res_lock = await self.session.execute(
                text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
                {"lock_key": current_lock_key},
            )
            lock_acquired = res_lock.scalar()
            if not lock_acquired:
                logger.warning(
                    "Advisory lock conflict on lock_key %s for event %s. Scheduling safe worker retry.",
                    current_lock_key,
                    event_id,
                )
                await self.session.rollback()
                raise LockAcquisitionException(
                    lock_key=current_lock_key,
                    resource_id=event_id,
                    retry_after=5,
                )

        # 3. Mark as PROCESSING and increment attempts
        event.processing_status = "PROCESSING"
        event.processing_attempts += 1
        await self.session.flush()

        # 4. Dispatch Event Processing
        try:
            now = _utc_now()
            event_type = event.event_type.lower()

            if event_type in ("payment.captured", "order.paid", "payment.authorized"):
                # Handle payment capture / settlement
                entity = (
                    event.payload.get("payload", {}).get("payment", {}).get("entity", {})
                    or event.payload.get("payment", {})
                )
                order_entity = (
                    event.payload.get("payload", {}).get("order", {}).get("entity", {})
                    or event.payload.get("order", {})
                )

                gateway_payment_id = entity.get("id") or event.payment_reference
                if not gateway_payment_id:
                    raise PaymentDomainException(
                        code="MISSING_PAYMENT_ID",
                        message="Webhook payload is missing gateway payment ID",
                    )

                # Amount in paise -> Decimal
                amount_paise = entity.get("amount") or order_entity.get("amount") or 0
                amount = (Decimal(str(amount_paise)) / Decimal("100")).quantize(Decimal("0.01"))
                currency = entity.get("currency") or order_entity.get("currency") or "INR"
                method = (entity.get("method") or "CARD").upper()

                # Card & UPI metadata
                card_data = entity.get("card") or {}
                card_network = card_data.get("network")
                card_last4 = card_data.get("last4")
                upi_vpa = entity.get("vpa")

                fee_paise = entity.get("fee") or 0
                tax_paise = entity.get("tax") or 0
                gateway_fee = (Decimal(str(fee_paise)) / Decimal("100")).quantize(Decimal("0.01"))
                gateway_tax = (Decimal(str(tax_paise)) / Decimal("100")).quantize(Decimal("0.01"))

                # Resolve Society & Invoice IDs
                notes = entity.get("notes") or order_entity.get("notes") or {}
                society_id_str = notes.get("society_id") or (
                    str(event.society_id) if event.society_id else None
                )
                invoice_id_str = notes.get("invoice_id")
                gateway_order_id = entity.get("order_id") or order_entity.get("id")

                society_id: UUID | None = None
                if society_id_str:
                    try:
                        society_id = UUID(str(society_id_str))
                    except (ValueError, AttributeError):
                        pass

                invoice_id: UUID | None = None
                if invoice_id_str:
                    try:
                        invoice_id = UUID(str(invoice_id_str))
                    except (ValueError, AttributeError):
                        pass

                # If invoice_id exists but society_id not in notes, look up invoice
                payment_attempt_id: UUID | None = None
                if gateway_order_id:
                    stmt_att = select(PlatformPaymentAttempt).where(
                        PlatformPaymentAttempt.gateway_order_id == gateway_order_id
                    )
                    attempt = (await self.session.execute(stmt_att)).scalar_one_or_none()
                    if attempt:
                        payment_attempt_id = attempt.id
                        if not society_id:
                            society_id = attempt.society_id
                        if not invoice_id:
                            invoice_id = attempt.invoice_id

                if not society_id and invoice_id:
                    stmt_inv = select(PlatformInvoice.society_id).where(PlatformInvoice.id == invoice_id)
                    society_id = (await self.session.execute(stmt_inv)).scalar_one_or_none()

                if not society_id:
                    raise PaymentDomainException(
                        code="UNRESOLVED_SOCIETY",
                        message=f"Cannot associate payment {gateway_payment_id} with any society.",
                    )

                # Execute settlement
                settled_payment = await self.settlement_service.settle_payment(
                    society_id=society_id,
                    gateway_provider=norm_provider,
                    gateway_payment_id=gateway_payment_id,
                    amount=amount,
                    invoice_id=invoice_id,
                    currency=currency,
                    payment_method=method,
                    captured_at=now,
                    card_network=card_network,
                    card_last4=card_last4,
                    upi_vpa=upi_vpa,
                    gateway_fee=gateway_fee,
                    gateway_tax=gateway_tax,
                    payment_attempt_id=payment_attempt_id,
                    custom_provider=custom_provider,
                )

                if settled_payment.reconciliation_status == "ORPHAN_ON_CANCELLED_SUBSCRIPTION":
                    event.processing_status = "PROCESSED_REFUND_INITIATED"
                else:
                    event.processing_status = "PROCESSED"

                event.processed_at = now
                event.last_error = None

            elif event_type in ("refund.processed", "refund.created", "refund.speed_changed"):
                # Handle refund notification
                entity = (
                    event.payload.get("payload", {}).get("refund", {}).get("entity", {})
                    or event.payload.get("refund", {})
                )
                gateway_refund_id = entity.get("id")
                if gateway_refund_id:
                    stmt_rf = select(PlatformRefund).where(
                        PlatformRefund.gateway_refund_id == gateway_refund_id
                    )
                    refund = (await self.session.execute(stmt_rf)).scalar_one_or_none()
                    if refund:
                        refund.status = "COMPLETED"
                        refund.processed_at = now

                event.processing_status = "PROCESSED"
                event.processed_at = now
                event.last_error = None

            else:
                # Informational / non-settlement event
                logger.info("Skipping non-settlement webhook event type '%s'", event.event_type)
                event.processing_status = "SKIPPED"
                event.processed_at = now
                event.last_error = None

            await self.session.commit()
            return event

        except Exception as exc:
            logger.error("Error processing webhook %s:%s: %s", norm_provider, event_id, exc)
            sanitized_err = str(exc)[:500]

            if event.processing_attempts >= MAX_RETRIES:
                event.processing_status = "FAILED"
                logger.error(
                    "Webhook %s:%s reached max retries (%s). Moving to FAILED (Dead Letter).",
                    norm_provider,
                    event_id,
                    MAX_RETRIES,
                )
            else:
                event.processing_status = "PENDING"  # Eligible for retry

            event.last_error = sanitized_err
            await self.session.commit()
            raise
