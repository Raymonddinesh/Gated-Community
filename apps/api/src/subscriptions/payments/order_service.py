"""Phase 21E.3 — Secure Server-Side Payment Order Creation Service.

Authoritative domain service for initiating gateway payment orders.
- Enforces server-side authority over payment amounts and invoice status.
- Idempotency protection prevents duplicate active checkout sessions.
- Tenant context and FORCE RLS isolation.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.src.core.tenant_context import tenant_context
from apps.api.src.database.models.platform_billing import (
    PlatformInvoice,
    PlatformPaymentAttempt,
)
from apps.api.src.database.models.subscription import SocietySubscription
from apps.api.src.database.session import set_db_tenant_context
from apps.api.src.subscriptions.payments.exceptions import (
    InvalidInvoiceStateException,
    InvoiceAlreadyPaidException,
    InvoiceNotFoundException,
    PaymentAlreadySettledException,
    PaymentOrderCreationException,
)
from apps.api.src.subscriptions.payments.provider import PaymentGatewayProvider
from apps.api.src.subscriptions.payments.provider_factory import PaymentGatewayFactory
from apps.api.src.subscriptions.payments.schemas import PaymentOrderResponse

logger = logging.getLogger("societysphere.payments.order")


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class PaymentOrderService:
    """Creates and manages authoritative server-side checkout payment orders."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_payment_order(
        self,
        society_id: UUID,
        invoice_id: UUID,
        idempotency_key: str | None = None,
        provider_name: str = "RAZORPAY",
        custom_provider: PaymentGatewayProvider | None = None,
    ) -> PaymentOrderResponse:
        """Create a server-side payment order for an authoritative platform invoice.

        Guarantees:
        - Invoice and tenant validation under FORCE RLS.
        - Strict amount authority (amount taken directly from invoice.amount_due).
        - Idempotency: replaying an active key returns the cached payment attempt.
        - Rejects already paid or void invoices.
        """
        async with tenant_context(society_id):
            await set_db_tenant_context(self.session, society_id)

            # 1. Check idempotency for existing active attempt
            if idempotency_key:
                stmt_existing = select(PlatformPaymentAttempt).where(
                    PlatformPaymentAttempt.society_id == society_id,
                    PlatformPaymentAttempt.idempotency_key == idempotency_key,
                )
                res_existing = await self.session.execute(stmt_existing)
                existing_attempt = res_existing.scalar_one_or_none()

                if existing_attempt:
                    if existing_attempt.status == "SUCCEEDED":
                        raise PaymentAlreadySettledException(payment_id=existing_attempt.gateway_order_id)
                    if existing_attempt.status in ("CREATED", "PROCESSING"):
                        now = _utc_now()
                        if existing_attempt.expires_at is None or existing_attempt.expires_at > now:
                            logger.info(
                                "Returning existing active payment attempt for idempotency key %s",
                                idempotency_key,
                            )
                            # Resolve provider public key ID
                            provider = custom_provider or await PaymentGatewayFactory.get_provider(
                                self.session, existing_attempt.gateway_provider
                            )
                            key_id = getattr(provider, "key_id", "rzp_test_public_key")
                            return PaymentOrderResponse(
                                attempt_id=existing_attempt.id,
                                invoice_id=existing_attempt.invoice_id,
                                gateway_provider=existing_attempt.gateway_provider,
                                order_id=existing_attempt.gateway_order_id,
                                amount=existing_attempt.amount,
                                currency_code=existing_attempt.currency_code,
                                key_id=key_id,
                                checkout_url=existing_attempt.checkout_url,
                                expires_at=existing_attempt.expires_at,
                            )

            # 2. Fetch and validate invoice under row lock
            stmt_invoice = (
                select(PlatformInvoice)
                .where(
                    PlatformInvoice.id == invoice_id,
                    PlatformInvoice.society_id == society_id,
                )
                .with_for_update()
            )
            res_invoice = await self.session.execute(stmt_invoice)
            invoice = res_invoice.scalar_one_or_none()
            if not invoice:
                raise InvoiceNotFoundException(invoice_id=invoice_id)

            if invoice.status == "PAID" or invoice.amount_due <= Decimal("0.00"):
                raise InvoiceAlreadyPaidException(invoice_id=invoice_id)

            if invoice.status in ("VOID", "UNCOLLECTIBLE"):
                raise InvalidInvoiceStateException(invoice_id=invoice_id, current_status=invoice.status)

            # 3. Validate society subscription
            stmt_sub = select(SocietySubscription).where(SocietySubscription.id == invoice.subscription_id)
            sub = (await self.session.execute(stmt_sub)).scalar_one_or_none()
            if not sub:
                raise PaymentOrderCreationException(
                    invoice_id=invoice_id,
                    reason="Associated society subscription was not found.",
                )

            # 4. Resolve gateway provider
            provider = custom_provider or await PaymentGatewayFactory.get_provider(
                self.session, provider_name
            )

            # 5. Authoritative amount & currency
            authoritative_amount = invoice.amount_due.quantize(Decimal("0.01"))
            currency_code = invoice.currency_code or "INR"
            receipt_id = f"rcpt_{invoice.id.hex[:12]}_{uuid.uuid4().hex[:6]}"

            notes: dict[str, Any] = {
                "society_id": str(society_id),
                "invoice_id": str(invoice_id),
                "subscription_id": str(sub.id),
                "invoice_number": invoice.invoice_number or "",
            }

            # 6. Call provider to create order
            gateway_order = await provider.create_payment_order(
                amount=authoritative_amount,
                currency=currency_code,
                receipt=receipt_id,
                notes=notes,
            )

            # 7. Persist payment attempt
            now = _utc_now()
            attempt = PlatformPaymentAttempt(
                society_id=society_id,
                invoice_id=invoice_id,
                gateway_provider=provider.provider_name,
                gateway_order_id=gateway_order.order_id,
                amount=authoritative_amount,
                currency_code=currency_code,
                status="CREATED",
                idempotency_key=idempotency_key or f"idem_{uuid.uuid4().hex}",
                expires_at=now + timedelta(minutes=30),
            )
            self.session.add(attempt)
            await self.session.flush()

            key_id = getattr(provider, "key_id", "rzp_test_public_key")

            return PaymentOrderResponse(
                attempt_id=attempt.id,
                invoice_id=invoice.id,
                gateway_provider=provider.provider_name,
                order_id=gateway_order.order_id,
                amount=authoritative_amount,
                currency_code=currency_code,
                key_id=key_id,
                checkout_url=None,
                expires_at=attempt.expires_at,
            )
